"""Долгая память: релевантность фактов, ограничение размера, голоса."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.memory import FactLog, voices_of  # noqa: E402


def test_relevance_by_entities():
    fl = FactLog()
    fl.add(1, "Марек отвернулся к стеклу", ["marek"])
    fl.add(2, "Ия плачет у печи", ["iya"])
    fl.add(3, "Марек снова молчит", ["marek"])
    r = fl.relevant(["marek"], k=5)
    assert len(r) == 2 and all("Марек" in t for t in r)


def test_relevance_empty_query():
    fl = FactLog()
    fl.add(1, "что-то", ["x"])
    assert fl.relevant([]) == []


def test_bounded_size():
    fl = FactLog(max_facts=3)
    for i in range(10):
        fl.add(i, f"fact {i}", ["x"])
    assert len(fl.facts) == 3


def test_voices_of():
    world = {"entities": {"marek": {"voice": "молчалив, короткие фразы"}, "iya": {"desc": "девочка"}}}
    assert voices_of(world, ["marek", "iya"]) == {"marek": "молчалив, короткие фразы"}


def test_select_budget_and_keys():
    fl = FactLog()
    fl.add(1, "Марек отвернулся к стеклу", ["marek"])
    fl.add(2, "Ия плачет у печи", ["iya"])
    fl.add(3, "Марек снова молчит", ["marek"])
    r = fl.select("Марек у стекла", entities=["marek"], budget=600)
    assert len(r) == 2 and all("Марек" in t for t in r)
    # бюджет (в символах) режет: помещается ровно один факт
    tight = fl.select("Марек", entities=["marek"], budget=len("Марек отвернулся к стеклу"))
    assert len(tight) == 1


if __name__ == "__main__":
    for fn in [test_relevance_by_entities, test_relevance_empty_query, test_bounded_size,
               test_voices_of, test_select_budget_and_keys]:
        fn()
        print("ok", fn.__name__)
