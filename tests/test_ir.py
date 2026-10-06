"""A: rich frontend (машины · время · агенты) понижается в ядро; B работает поверх."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.abstract import prove  # noqa: E402
from sintgame.ir import compile_game  # noqa: E402
from sintgame.kernel import World  # noqa: E402

BASE = {"entities": {"player": {"type": "actor", "tags": ["player"], "attrs": {"hp": 10, "gold": 0}}},
        "holds": [], "relations": [], "flags": {}}


def test_machine_region_transition():
    spec = dict(BASE, flags={"has_key": 0},
                actions=[{"id": "take_key", "label": "взять", "pre": [], "eff": [["flag", "has_key", 1]]}],
                machines={"door": {"initial": "locked", "regions": ["locked", "open"],
                                   "transitions": [{"from": "locked", "to": "open",
                                                    "pre": [["flag", "has_key"]]}]}})
    w = World(compile_game(spec))
    assert w.flags.get("m_door_locked") == 1 and w.flags.get("m_door_open") == 0
    w.act("take_key")
    assert w.flags.get("m_door_open") == 1 and w.flags.get("m_door_locked") == 0


def test_time_periodic():
    spec = dict(BASE, actions=[],
                time={"carrier": "player", "cooldowns": {"day": 3},
                      "periodic": [{"cd": "day", "eff": [["add", "player.gold", 1]]}]})
    w = World(compile_game(spec))
    for _ in range(9):
        w.tick()
    assert w.get("player.gold") == 3


def test_hidden_tick_not_in_menu():
    spec = dict(BASE, actions=[],
                time={"carrier": "player", "cooldowns": {"t": 5}, "periodic": []})
    w = World(compile_game(spec))
    assert all(a["id"] != "__tick__" for a in w.available())


def test_agents_filter():
    spec = dict(BASE, entities={"player": {"type": "actor", "tags": ["player"], "attrs": {"hp": 10}},
                                "rival": {"type": "actor", "tags": ["npc"], "attrs": {"hp": 10}}},
                actions=[{"id": "us", "label": "u", "pre": [], "eff": [["say", "u"]], "agent": "us"},
                         {"id": "them", "label": "t", "pre": [], "eff": [["say", "t"]], "agent": "them"}])
    w = World(compile_game(spec))
    assert [a["id"] for a in w.available("us")] == ["us"]
    assert [a["id"] for a in w.available("them")] == ["them"]


def test_abstract_proves_machine_and_time():
    # концовка достижима: взять ключ (действие) -> машина открывает дверь -> концовка
    spec = dict(BASE, flags={"key": 0},
                actions=[{"id": "take", "label": "t", "pre": [], "eff": [["flag", "key", 1]]},
                         {"id": "win", "label": "win", "pre": [["flag", "m_door_open"]],
                          "eff": [["end", "win"]]}],
                machines={"door": {"initial": "locked", "regions": ["locked", "open"],
                                   "transitions": [{"from": "locked", "to": "open",
                                                    "pre": [["flag", "key"]]}]}})
    r = prove(compile_game(spec))
    assert "win" in r["reachable_abs"], r

    # концовка недостижима: регион b недостижим -> доказательство
    spec2 = dict(BASE, flags={},
                 actions=[{"id": "win", "label": "win", "pre": [["flag", "m_x_b"]],
                           "eff": [["end", "win"]]}],
                 machines={"x": {"initial": "a", "regions": ["a", "b"], "transitions": []}})
    r2 = prove(compile_game(spec2))
    assert r2["proven_unreachable"] == ["win"], r2


def test_hierarchical_machine():
    spec = dict(BASE, flags={"key": 0},
                actions=[{"id": "go", "label": "g", "pre": [], "eff": [["flag", "key", 1]]}],
                machines={"outer": {
                    "initial": "closed", "regions": ["closed", "open"],
                    "transitions": [{"from": "closed", "to": "open", "pre": [["flag", "key"]]}],
                    "children": {"inner": {
                        "when": "open", "initial": "dark", "regions": ["dark", "lit"],
                        "transitions": [{"from": "dark", "to": "lit", "pre": [["flag", "key"]]}]}}}})
    w = World(compile_game(spec))
    assert w.flags.get("m_outer_closed") == 1 and w.flags.get("m_outer_inner_dark") == 1
    w.act("go")
    assert w.flags.get("m_outer_open") == 1
    assert w.flags.get("m_outer_inner_lit") == 1


if __name__ == "__main__":
    for fn in [test_machine_region_transition, test_time_periodic, test_hidden_tick_not_in_menu,
               test_agents_filter, test_abstract_proves_machine_and_time, test_hierarchical_machine]:
        fn()
        print("ok", fn.__name__)
