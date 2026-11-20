"""Full 089E loss movie/resources/promotion, EGA and VGA; streaming/camera explicit."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_egaplayer, test_vgaplayer
CASES = 0

def run(ctx):
    global CASES
    CASES = 0
    for module in [test_egaplayer, test_vgaplayer]:
        fails = module.run(ctx, opponent=True, losses=True)
        CASES += module.CASES
        if fails:
            return [module.__name__+': '+f for f in fails]
    return []
