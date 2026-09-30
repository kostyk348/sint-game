"""Прогон: N ходов (многоэпизодно), без нарушений инвариантов."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.run import POLICIES, soak  # noqa: E402

WORLD = json.load(open(os.path.join(ROOT, "examples", "lighthouse", "world.json")))


def test_soak_reaches_50_turns():
    r = soak(WORLD, turns=50, policy="explore", seed=0)
    assert r["turns"] == 50, r
    assert r["episodes"] >= 2, "мир короткий — должно быть несколько эпизодов"
    assert r["violations"] == [], r["violations"]


def test_soak_all_policies_run_clean():
    for p in POLICIES:
        r = soak(WORLD, turns=30, policy=p, seed=1)
        assert r["turns"] >= 30 or r["turns"] > 0
        assert r["violations"] == [], (p, r["violations"])


if __name__ == "__main__":
    for fn in [test_soak_reaches_50_turns, test_soak_all_policies_run_clean]:
        fn()
        print("ok", fn.__name__)
