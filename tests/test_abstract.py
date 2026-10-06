"""Звучий анализ: доказательство недостижимости, инварианты, liveness + надмножество."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.abstract import prove  # noqa: E402
from sintgame.search import reachability  # noqa: E402

EX = os.path.join(ROOT, "examples")


def _load(name):
    return json.load(open(os.path.join(EX, name, "world.json")))


def test_examples_safe_and_all_reachable():
    for name in ("lighthouse", "station"):
        r = prove(_load(name))
        assert r["proven_unreachable"] == [], (name, r)
        assert r["invariant_may_violate"] is False, (name, r)
        assert r["dead_end_possible"] is False, (name, r)
        assert set(r["declared"]) <= set(r["reachable_abs"]), (name, r)


def test_soundness_abstract_is_superset_of_concrete():
    # всё, что достижимо КОНКРЕТНО со свидетелем, обязано быть достижимо в абстракции
    for name in ("lighthouse", "station"):
        d = _load(name)
        concrete = set(reachability(d)["reachable"].keys())
        abstract = set(prove(d)["reachable_abs"])
        assert concrete <= abstract, (name, concrete - abstract)


def test_proven_unreachable_ending():
    d = {
        "seed": 1,
        "entities": {"player": {"type": "actor", "tags": ["player"], "attrs": {"hp": 10}}},
        "holds": [], "relations": [], "flags": {"f": 0},
        "actions": [
            {"id": "a", "label": "a", "pre": [], "eff": [["flag", "f", 1]]},
            # концовка требует флага g, который нигде не выставляется -> недостижима
            {"id": "win", "label": "win", "pre": [["flag", "g"]], "eff": [["end", "win"]]},
        ],
        "triggers": [],
    }
    r = prove(d)
    assert r["proven_unreachable"] == ["win"], r


def test_invariant_violation_detected():
    d = {
        "seed": 1,
        "entities": {"player": {"type": "actor", "tags": ["player"], "attrs": {"hp": 10}},
                     "king": {"type": "actor", "tags": ["npc"], "attrs": {"hp": 5}}},
        "holds": [], "relations": [], "flags": {},
        "actions": [
            {"id": "kill", "label": "kill", "pre": [], "eff": [["dmg", "king", 40]]},
        ],
        "triggers": [],
        "constraints": {"vital": ["king"], "min_hp": 1},
    }
    r = prove(d)
    assert r["invariant_may_violate"] is True, r


def test_safe_invariant_not_flagged():
    d = {
        "seed": 1,
        "entities": {"player": {"type": "actor", "tags": ["player"], "attrs": {"hp": 10}},
                     "king": {"type": "actor", "tags": ["npc"], "attrs": {"hp": 5}}},
        "holds": [], "relations": [], "flags": {},
        # бьём только пока hp>2 -> ниже 2 не опустится -> инвариант цел
        "actions": [{"id": "poke", "label": "poke", "pre": [["gt", "king.hp", 2]],
                     "eff": [["dmg", "king", 1]]}],
        "triggers": [],
        "constraints": {"vital": ["king"], "min_hp": 1},
    }
    r = prove(d)
    assert r["invariant_may_violate"] is False, r


if __name__ == "__main__":
    for fn in [test_examples_safe_and_all_reachable, test_soundness_abstract_is_superset_of_concrete,
               test_proven_unreachable_ending, test_invariant_violation_detected,
               test_safe_invariant_not_flagged]:
        fn()
        print("ok", fn.__name__)
