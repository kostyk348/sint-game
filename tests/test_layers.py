"""Слоёная память: постоянные + мир + сага под ОДНИМ бюджетом."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.lorebook import LayeredMemory, Lorebook  # noqa: E402
from sintgame.memory import layering, saga_layer  # noqa: E402


def test_constants_always_present():
    m = LayeredMemory(budget=1000)
    m.add_constant("identity")
    m.set("world", Lorebook([{"id": "w", "keys": ["marek"], "content": "Мир: Марек", "priority": 0}]))
    r = m.select("Марек", entities=["marek"], budget=1000)
    assert r[0] == "identity"
    assert any("Марек" in x for x in r)


def test_two_layers_share_budget():
    world = Lorebook([{"id": "w1", "keys": ["marek"], "content": "A" * 50, "priority": 0}])
    saga = Lorebook([{"id": "s1", "keys": ["marek"], "content": "B" * 50, "priority": 1}])
    m = LayeredMemory()
    m.set("world", world)
    m.set("saga", saga)
    assert len(m.select("Марек", entities=["marek"], budget=1000)) == 2
    # бюджет (символы) режет второй слой
    assert len(m.select("Марек", entities=["marek"], budget=50)) == 1


def test_layering_helper_merges_three_sources():
    world = {"title": "Маяк", "tone": "cold",
             "entities": {"marek": {"desc": "смотритель", "voice": "сухо"}}}
    facts = [{"turn": 1, "text": "Марек ушёл к морю", "entities": ["marek"]}]
    m = layering(world, saga_layer(facts), budget=1000)
    r = m.select("Марек", entities=["marek"], budget=1000)
    assert any("Маяк" in x for x in r), r        # constant (ядро)
    assert any("смотритель" in x for x in r), r  # мир (статика)
    assert any("ушёл" in x for x in r), r        # сага (долгие факты)


if __name__ == "__main__":
    for fn in [test_constants_always_present, test_two_layers_share_budget,
               test_layering_helper_merges_three_sources]:
        fn()
        print("ok", fn.__name__)
