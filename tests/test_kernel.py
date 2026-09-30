"""Ядро: детерминизм, отказ при ложном pre, save/load включая rng."""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.kernel import World  # noqa: E402

EX = os.path.join(ROOT, "examples")

DICE = {"seed": 7,
        "entities": {"player": {"attrs": {"hp": 100, "str": 3}}, "foe": {"attrs": {"hp": 100}}},
        "flags": {}, "holds": [], "relations": [],
        "actions": [{"id": "hit", "label": "hit", "pre": [],
                     "eff": [["dmg", "foe", {"roll": "1d8", "plus": "player.str"}]]}],
        "triggers": []}


def test_same_seed_same_rolls():
    a, b = World(copy.deepcopy(DICE)), World(copy.deepcopy(DICE))
    assert [a.roll({"roll": "2d6"}) for _ in range(5)] == [b.roll({"roll": "2d6"}) for _ in range(5)]


def test_act_refuses_false_pre():
    w = World(copy.deepcopy(DICE))
    w.flags["done"] = 1
    w.d["actions"].append({"id": "once", "label": "once",
                           "pre": [["not", ["flag", "done"]]], "eff": [["say", "x"]]})
    assert not w.can("once")
    assert w.act("once") == []
    assert w.last_error == "unavailable"


def test_save_load_includes_rng():
    a = World(copy.deepcopy(DICE))
    for _ in range(5):
        a.act("hit")
    straight = a.get("foe.hp")

    b = World(copy.deepcopy(DICE))
    for _ in range(2):
        b.act("hit")
    st = b.state()
    for _ in range(3):
        b.act("hit")
    assert b.get("foe.hp") == straight, "без save/load последовательность должна сойтись"

    c = World(copy.deepcopy(DICE))
    c.restore(st)
    for _ in range(3):
        c.act("hit")
    assert c.get("foe.hp") == straight, "restore(state) должен продолжить ровно так же"


def test_replay_deterministic():
    world = json.load(open(os.path.join(EX, "lighthouse", "world.json")))

    def run():
        w = World(copy.deepcopy(world))
        for a in ["talk_iya", "feed_stove", "search_cabin", "go_to_wreck", "wait_out_storm"]:
            if w.can(a):
                w.act(a)
        return w.state()

    assert run() == run()


if __name__ == "__main__":
    for fn in [test_same_seed_same_rolls, test_act_refuses_false_pre,
               test_save_load_includes_rng, test_replay_deterministic]:
        fn()
        print("ok", fn.__name__)
