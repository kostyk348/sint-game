"""Создание контента: merge + верификация (оффлайн, генератор инъектируется)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.content import add_content, verify  # noqa: E402

WORLD = json.load(open(os.path.join(ROOT, "examples", "lighthouse", "world.json")))


def _fresh():
    return json.loads(json.dumps(WORLD))


def test_good_npc_accepted():
    def gen(world, suffix):
        return {"entities": {"stranger": {"type": "actor", "tags": ["npc"],
                                          "attrs": {"hp": 10, "hp_max": 10}, "desc": "Странник"}},
                "relations": [["stranger", "player", "met", 1]]}

    w2, info = add_content(_fresh(), "npc", 1, generator=gen)
    assert w2 is not None and "stranger" in w2["entities"]
    assert verify(w2) == []


def test_good_quest_accepted():
    def gen(world, suffix):
        return {"flags": {"q_started": 0, "q_done": 0},
                "actions": [
                    {"id": "q_start", "label": "Начать поиск",
                     "pre": [["not", ["flag", "q_started"]]],
                     "eff": [["flag", "q_started", 1], ["say", "Ты решаешь искать."]]},
                    {"id": "q_finish", "label": "Завершить поиск",
                     "pre": [["flag", "q_started"], ["not", ["flag", "q_done"]]],
                     "eff": [["flag", "q_done", 1], ["rel", "iya", "player", "trust", 2]]}],
                "triggers": []}

    w2, info = add_content(_fresh(), "quest", 1, generator=gen)
    assert w2 is not None and verify(w2) == []


def test_duplicate_id_rejected():
    def gen(world, suffix):
        return {"entities": {"player": {"type": "actor", "tags": [], "attrs": {"hp": 1}}}}

    w2, info = add_content(_fresh(), "npc", 1, rounds=1, generator=gen)
    assert w2 is None and any("exists" in e for e in info)


def test_dangling_flag_rejected():
    def gen(world, suffix):
        return {"flags": {"q": 0},
                "actions": [{"id": "q_go", "label": "идти",
                             "pre": [["flag", "nonexistent_flag"]],
                             "eff": [["flag", "q", 1]]}]}

    w2, info = add_content(_fresh(), "quest", 1, rounds=1, generator=gen)
    assert w2 is None and any("dangling" in e for e in info)


def test_no_json_rejected():
    w2, info = add_content(_fresh(), "npc", 1, rounds=1, generator=lambda w, s: None)
    assert w2 is None and info == ["generator returned no JSON"]


if __name__ == "__main__":
    for fn in [test_good_npc_accepted, test_good_quest_accepted, test_duplicate_id_rejected,
               test_dangling_flag_rejected, test_no_json_rejected]:
        fn()
        print("ok", fn.__name__)
