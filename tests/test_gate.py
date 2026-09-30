"""Ворота: структурные + авторские инварианты (vital)."""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame import intent as I  # noqa: E402
from sintgame.kernel import World  # noqa: E402

WORLD = json.load(open(os.path.join(ROOT, "examples", "lighthouse", "world.json")))

CASES = [
    ("lethal via dmg", {"id": "k1", "label": "x", "pre": [], "eff": [["dmg", "marek", 40]]}, True),
    ("lethal via dead-flag", {"id": "k2", "label": "x", "pre": [], "eff": [["flag", "marek_dead", 1]]}, True),
    ("creates new ending", {"id": "k3", "label": "x", "pre": [], "eff": [["end", "newend"]]}, True),
    ("delta out of bounds", {"id": "k4", "label": "x", "pre": [], "eff": [["add", "player.hp", 999]]}, True),
    ("unknown entity", {"id": "k5", "label": "x", "pre": [], "eff": [["dmg", "ghost", 5]]}, True),
    ("no effects", {"id": "k6", "label": "x", "pre": [], "eff": []}, True),
    ("bad op", {"id": "k7", "label": "x", "pre": [], "eff": [["teleport", "player", "home"]]}, True),
    ("warm, legal", {"id": "hug", "label": "обнять", "pre": [],
                     "eff": [["heal", "iya", 3], ["rel", "iya", "player", "bond", 5]]}, False),
]


def test_gate_invariants():
    w = World(copy.deepcopy(WORLD))
    for name, action, expect_reject in CASES:
        errs = I.gate(action, WORLD, w)
        assert bool(errs) == expect_reject, f"{name}: {errs or 'ADMIT'}"


if __name__ == "__main__":
    test_gate_invariants()
    print(f"ok test_gate_invariants ({len(CASES)} cases)")
