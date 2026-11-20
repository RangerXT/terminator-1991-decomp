"""Native vehicleentry with actual resource files; BIOS/stat/stream boundaries independent."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_vehicletransition as base
CASES = 0
def run(ctx):
    global CASES
    base.CASES = 0
    result = base.run(ctx, caller="entry")
    CASES = base.CASES
    return result
