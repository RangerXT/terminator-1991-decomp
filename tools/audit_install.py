"""Verify the installed data against the four original level-0 LHA archives."""

import argparse
from pathlib import Path
import struct
import sys


ARCHIVES = {
    "common.exe": "common",
    "ega.exe": "ega",
    "vga1.exe": "vga",
    "vga2.exe": "vga",
}


def crc_table():
    table = []
    for value in range(256):
        for _ in range(8):
            polynomial = 0xA001 if value & 1 else 0
            value = (value >> 1) ^ polynomial
        table.append(value)
    return table


CRC_TABLE = crc_table()


def file_crc(path):
    value = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            for byte in chunk:
                value = (value >> 8) ^ CRC_TABLE[(value ^ byte) & 255]
    return value


def members(path):
    data = path.read_bytes()
    if len(data) < 28 or data[:2] != b"MZ":
        raise ValueError("missing DOS executable header")
    last_page, pages = struct.unpack_from("<HH", data, 2)
    if pages == 0 or last_page > 511:
        raise ValueError("invalid DOS executable length")
    offset = (pages - 1) * 512 + (last_page or 512)
    if not 28 <= offset < len(data):
        raise ValueError("archive overlay is outside the file")

    while data[offset]:
        header_size = data[offset]
        payload = offset + 2 + header_size
        header = data[offset + 2:payload]
        if header_size < 22 or payload > len(data):
            raise ValueError(f"truncated member header at {offset:#x}")
        if header[18] != 0 or sum(header) & 255 != data[offset + 1]:
            raise ValueError(f"invalid level-0 member header at {offset:#x}")
        method = header[:5].decode("ascii")
        if method not in ("-lh0-", "-lh5-"):
            raise ValueError(f"unsupported member method {method!r}")
        packed, length = struct.unpack_from("<II", header, 5)
        end = payload + packed
        name_end = 20 + header[19]
        if name_end + 2 > len(header) or end >= len(data):
            raise ValueError(f"truncated member at {offset:#x}")
        name = header[20:name_end].decode("ascii")
        checksum, = struct.unpack_from("<H", header, name_end)
        yield name, length, checksum
        offset = end

    if offset != len(data) - 1:
        raise ValueError("unexpected bytes after archive terminator")


def audit(root):
    inventory = {}
    archived = {}
    for folder in dict.fromkeys(ARCHIVES.values()):
        inventory[folder] = {p.name.upper(): p for p in (root / "data" / folder).iterdir() if p.is_file()}
        archived[folder] = set()

    total = 0
    errors = []
    for archive, folder in ARCHIVES.items():
        matched = 0
        count = 0
        for name, length, checksum in members(root / archive):
            key = name.upper()
            count += 1
            if key in archived[folder]:
                errors.append(f"{archive}/{name}: duplicate archived name")
                continue
            archived[folder].add(key)
            path = inventory[folder].get(key)
            if path is None:
                errors.append(f"{archive}/{name}: missing from data/{folder}")
            elif path.stat().st_size != length or file_crc(path) != checksum:
                errors.append(f"{archive}/{name}: length or CRC differs")
            else:
                matched += 1
        total += matched
        print(f"{archive}: {matched} of {count} members match")

    for folder, paths in inventory.items():
        for name in sorted(paths.keys() - archived[folder]):
            errors.append(f"data/{folder}/{paths[name].name}: absent from archive")
    for error in errors:
        print(error, file=sys.stderr)
    print(f"{total} files verified against their archived size and CRC")
    return bool(errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    root = parser.parse_args().root
    try:
        return audit(root)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
