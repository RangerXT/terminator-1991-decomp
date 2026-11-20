"""Native C21F/B7B6/DB26/B5F9 against vehicle targets, with healthy vehicle reserve.
Destruction/resource chains are covered separately by test_vehiclefire.
"""
import importlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CASES = 0

def run(ctx):
    global CASES
    CASES = 0
    for name in ['opponentai', 'opponentslow', 'companionai', 'worldstep', 'travelworld']:
        module = importlib.import_module('test_'+name)
        fails = module.run(ctx, vehicle=True)
        CASES += module.CASES
        if fails:
            return [name+': '+f for f in fails]
    return []
