"""0641 pre-render collision, actual walking warning and vehicle ejection."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_vehicletransition as base

CASES = 0


def run(ctx):
    global CASES
    base.CASES = 0
    failures = base.run(ctx, caller='predraw')
    CASES = base.CASES
    return failures
