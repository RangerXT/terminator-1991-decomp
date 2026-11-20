"""Complete proximity/key/menu/transfer/refresh pickup flow against original 884B."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_pickupmenu as base
CASES = 0
def run(ctx):
    global CASES
    base.CASES = 0
    result = base.run(ctx, controller=True)
    CASES = base.CASES
    return result
