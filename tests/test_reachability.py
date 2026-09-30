"""Достижимость: BFS со свидетелями + статический анализ предусловий."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import json  # noqa: E402

from sintgame.search import dangling_prerequisites, declared_endings, reachability  # noqa: E402

EX = os.path.join(ROOT, "examples")


def _load(name):
    return json.load(open(os.path.join(EX, name, "world.json")))


def test_lighthouse_all_reachable_with_witnesses():
    d = _load("lighthouse")
    r = reachability(d)
    assert len(r["reachable"]) == len(declared_endings(d)) == 4
    assert r["not_found"] == []
    for path in r["reachable"].values():
        assert path and len(path) <= 8


def test_station_all_reachable_with_witnesses():
    d = _load("station")
    r = reachability(d)
    assert len(r["reachable"]) == len(declared_endings(d)) == 4
    assert r["not_found"] == []


def test_dangling_flag_detected():
    d = {"seed": 1,
         "entities": {"player": {"attrs": {"hp": 10}}},
         "flags": {}, "holds": [], "relations": [],
         "actions": [{"id": "go", "label": "go",
                      "pre": [["flag", "never_set"]],
                      "eff": [["end", "win"]]}],
         "triggers": []}
    assert dangling_prerequisites(d)["flags_required_but_never_set"] == ["never_set"]
    r = reachability(d)
    assert r["not_found"] == ["win"]


def test_proven_unreachable_when_exhausted():
    d = {"seed": 1,
         "entities": {"player": {"attrs": {"hp": 10}}},
         "flags": {"gate": 0}, "holds": [], "relations": [],
         "actions": [
             {"id": "idle", "label": "idle", "pre": [["not", ["flag", "done"]]],
              "eff": [["flag", "done", 1]]},
             {"id": "win", "label": "win", "pre": [["flag", "gate"]], "eff": [["end", "win"]]},
         ],
         "triggers": []}
    r = reachability(d, stop_when_all_found=False)
    assert r["exhausted"] is True
    assert r["unreachable"] == ["win"]


if __name__ == "__main__":
    for fn in [test_lighthouse_all_reachable_with_witnesses, test_station_all_reachable_with_witnesses,
               test_dangling_flag_detected, test_proven_unreachable_when_exhausted]:
        fn()
        print("ok", fn.__name__)
