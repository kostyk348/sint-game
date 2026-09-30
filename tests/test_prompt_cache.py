"""Prompt-cache: префикс стабилен через admitted-действия; наивный — ломается."""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame import prompt as P  # noqa: E402

WORLD = json.load(open(os.path.join(ROOT, "examples", "lighthouse", "world.json")))


def test_prefix_stable_across_admitted():
    w = json.loads(json.dumps(WORLD))
    h0 = P.prefix_hash(P.world_bible(w))
    w.setdefault("actions", []).append(
        {"id": "hug_iya", "label": "обнять", "pre": [], "eff": [["heal", "iya", 3]]})
    assert P.prefix_hash(P.world_bible(w)) == h0, "admitted-действие не должно ломать префикс"


def test_prefix_shared_by_callers():
    # все рантайм-вызовы делят один префикс на мир
    assert P.world_bible(WORLD) == P.world_bible(WORLD)


def test_naive_full_world_prefix_breaks():
    w = json.loads(json.dumps(WORLD))
    h0 = hashlib.sha1(json.dumps(w, sort_keys=True).encode()).hexdigest()
    w["actions"].append({"id": "x", "label": "x", "pre": [], "eff": [["say", "x"]]})
    assert hashlib.sha1(json.dumps(w, sort_keys=True).encode()).hexdigest() != h0


if __name__ == "__main__":
    for fn in [test_prefix_stable_across_admitted, test_prefix_shared_by_callers,
               test_naive_full_world_prefix_breaks]:
        fn()
        print("ok", fn.__name__)
