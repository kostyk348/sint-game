"""Temporal: достижимость «за <= K шагов» (звучий горизонт), в т.ч. через время."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.abstract import horizon, prove  # noqa: E402
from sintgame.ir import compile_game  # noqa: E402


def test_horizon_on_real_world():
    d = json.load(open(os.path.join(ROOT, "examples", "lighthouse", "world.json")))
    h1 = horizon(d, 1)
    assert "truth" in h1["not_within_k"], h1        # за 1 шаг не достичь — доказано
    h5 = horizon(d, 5)
    assert "truth" in h5["within"], h5              # за 5 — достижимо в абстракции
    assert h5["not_within_k"] == [], h5


def test_horizon_time_gated_ending():
    spec = {
        "entities": {"player": {"type": "actor", "tags": ["player"], "attrs": {"hp": 10}}},
        "flags": {"ready": 0},
        "actions": [{"id": "win", "label": "w", "pre": [["flag", "ready"]], "eff": [["end", "win"]]}],
        "time": {"carrier": "player", "cooldowns": {"cd": 3},
                 "periodic": [{"cd": "cd", "eff": [["flag", "ready", 1]]}]},
    }
    w = compile_game(spec)
    h1 = horizon(w, 1)
    assert "win" in h1["not_within_k"], h1          # нельзя завершить за 1 шаг
    h4 = horizon(w, 4)
    assert "win" in h4["within"], h4                # с временем — достижимо
    assert prove(w)["proven_unreachable"] == []     # и вообще достижимо


if __name__ == "__main__":
    for fn in [test_horizon_on_real_world, test_horizon_time_gated_ending]:
        fn()
        print("ok", fn.__name__)
