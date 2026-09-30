"""Примеры: валидны, концовки достижимы, тупиков нет."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.schema import simulate, validate  # noqa: E402

EX = os.path.join(ROOT, "examples")


def _check(name):
    d = json.load(open(os.path.join(EX, name, "world.json")))
    assert validate(d) == [], f"{name}: {validate(d)}"
    sim = simulate(d, trials=200)
    assert len(sim["endings_reached"]) >= 2, f"{name}: мало достижимых концовок {sim}"
    assert sim["dead_ends"] == 0, f"{name}: тупики {sim}"
    assert sim["unstable"] == 0, f"{name}: нестабильные триггеры {sim}"
    return sim


def test_lighthouse():
    assert len(_check("lighthouse")["endings_reached"]) == 4


def test_station():
    assert len(_check("station")["endings_reached"]) == 4


if __name__ == "__main__":
    for fn in [test_lighthouse, test_station]:
        fn()
        print("ok", fn.__name__)
