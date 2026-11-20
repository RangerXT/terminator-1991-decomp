"""Basic VGA menu handlers with native saved-window restore."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_menuactions
CASES = 0

def run(ctx):
    global CASES
    fails = test_menuactions.run(ctx, vga=True)
    CASES = test_menuactions.CASES
    return fails
