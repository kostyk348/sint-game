"""Песочница: открытый мир (без концовок), долгий непрерывный прогон, директор."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.run import _choose  # noqa: F401,E402
from sintgame.sandbox import endurance  # noqa: E402
from sintgame.schema import validate  # noqa: E402
from sintgame.search import report as reach_report  # noqa: E402

CAMPAIGN = json.load(open(os.path.join(ROOT, "examples", "campaign", "world.json")))

OPEN = {"schema": 1, "title": "Песок", "seed": 1,
        "entities": {"player": {"type": "actor", "tags": ["player"], "attrs": {"hp": 10}}},
        "holds": [], "relations": [], "flags": {"n": 0},
        "actions": [{"id": "wait", "label": "Ждать", "pre": [], "eff": [["add", "n", 1]]}],
        "triggers": []}


def _stub_director(world, summary):
    n = len(world["actions"])
    return {"actions": [{"id": f"ev_{n}", "label": "Случайное событие",
                         "pre": [], "eff": [["say", "Что-то происходит на краю пустыни."]]}]}


def test_open_world_without_endings_is_valid():
    assert validate(OPEN) == []
    assert "OPEN WORLD" in reach_report(OPEN)[0]


def test_endurance_500_turns_single_episode():
    r = endurance(CAMPAIGN, turns=500, policy="linger", seed=0)
    assert r["turns"] >= 500, r
    assert r["dead_ends"] == 0
    assert r["violations"] == [], r["violations"][:3]


def test_director_grows_world():
    r = endurance(CAMPAIGN, turns=300, policy="linger", seed=0, director=_stub_director, every=100)
    assert r["director_calls"] >= 2
    assert r["actions_added"] >= 2
    assert r["violations"] == [], r["violations"][:3]


if __name__ == "__main__":
    for fn in [test_open_world_without_endings_is_valid, test_endurance_500_turns_single_episode,
               test_director_grows_world]:
        fn()
        print("ok", fn.__name__)
