"""Лорбук: активация по ключам, рекурсия, постоянные, бюджет, схема под логиты."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.lorebook import Lorebook  # noqa: E402

LB = Lorebook([
    {"id": "k_cold", "keys": ["холод", "зима"], "content": "зима лютая, лёд сковывает скалы",
     "priority": 0, "constant": True, "recursive": False},
    {"id": "e_marek", "keys": ["марек"], "content": "Марек, виноватый смотритель маяка, знает про журнал",
     "priority": 1, "constant": False, "recursive": True},
    {"id": "e_journal", "keys": ["журнал"], "content": "судовой журнал «Соли» подделан",
     "priority": 0, "constant": False, "recursive": False},
    {"id": "e_iya", "keys": ["ия", "девочка"], "content": "Ия ищет отца с корабля «Соль»",
     "priority": 0, "constant": False, "recursive": False},
])


def test_constant_always_active():
    assert "k_cold" in LB.scan("тишина")


def test_key_activation():
    assert "e_iya" in LB.scan("Ия плачет")


def test_recursive_activation():
    # активирован Марек -> в его тексте есть «журнал» -> тянет запись журнала
    ids = LB.scan("Марек молчит")
    assert "e_marek" in ids and "e_journal" in ids, ids


def test_budget_limits():
    chosen = LB.select("Марек молчит", budget=20)
    assert len(chosen) == 1, chosen       # мало бюджета -> берём только верхнюю


def test_selection_schema_shape():
    ids = sorted(LB.scan("Марек"))
    schema = LB.selection_schema(ids)
    assert set(schema["properties"].keys()) == set(ids)
    assert schema["required"] == ids
    assert all(v == {"type": "boolean"} for v in schema["properties"].values())


def test_apply_logit_decision():
    ids = ["a", "b", "c"]
    assert Lorebook.apply(ids, {"a": True, "b": False, "c": True}) == ["a", "c"]


def test_finalize_forces_constants():
    ids = ["k_cold", "e_marek", "e_iya"]
    # логиты выбрали только e_iya; константа k_cold обязана остаться
    assert Lorebook.finalize(ids, {"k_cold": False, "e_marek": False, "e_iya": True},
                             constants=["k_cold"]) == ["k_cold", "e_iya"]


def test_from_facts():
    lb = Lorebook.from_facts([{"turn": 1, "text": "Марек соврал", "entities": ["marek"]},
                              {"turn": 2, "text": "Ия плачет", "entities": ["iya"]}])
    assert len(lb.entries) == 2
    assert "fact_1_0" in lb.scan("marek")


if __name__ == "__main__":
    for fn in [test_constant_always_active, test_key_activation, test_recursive_activation,
               test_budget_limits, test_selection_schema_shape, test_apply_logit_decision,
               test_finalize_forces_constants, test_from_facts]:
        fn()
        print("ok", fn.__name__)
