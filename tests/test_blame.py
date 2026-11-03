"""blame.py — контрфактическая атрибуция гейтов: ранжирование по приросту концовки.

Синтетический мир, где ответ доказуем: escape_rich достижим только через
тройную удачу случайной политики (все три хода grab_cash), а снятие гейта
["ge","player.gold",500] у action escape открывает концовку с первого хода.
"""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.blame import blame, endings_universe, gates, report  # noqa: E402
from sintgame.kernel import World  # noqa: E402

WORLD = {
    "schema": 1,
    "seed": 0,
    "entities": {"player": {"type": "pc", "attrs": {"gold": 100}}},
    "actions": [
        {"id": "grab_cash", "label": "grab cash", "pre": [["ge", "player.gold", 100]],
         "eff": [["add", "player.gold", 200]]},
        {"id": "escape", "label": "escape rich", "pre": [["ge", "player.gold", 500]],
         "eff": [["end", "escape_rich"]]},
        {"id": "sneak_out", "label": "sneak out", "pre": [],
         "eff": [["end", "escape_poor"]]},
    ],
    "triggers": [
        {"pre": [["flag", "rich"]], "eff": [["say", "you feel rich"]], "once": True},
    ],
}

PARAMS = dict(trials=120, depth=30, seed0=500)


def test_base_rate_matches_the_proof():
    # escape_rich требует трёх подряд grab_cash: (1/2)^3 = 12.5% теоретически
    res = blame(copy.deepcopy(WORLD), "escape_rich", **PARAMS)
    assert 0.03 <= res["base_rate"] <= 0.30, res["base_rate"]


def test_relaxing_the_escape_gate_unlocks_it():
    res = blame(copy.deepcopy(WORLD), "escape_rich", **PARAMS)
    assert res["gates"], "атрибуция не должна быть пустой"
    top = res["gates"][0]
    assert top["cond"] == ["ge", "player.gold", 500]
    assert top["action"] == "escape"
    assert top["rate_after"] > res["base_rate"] + 0.25
    # декой-гейт grab_cash всегда истинен при gold>=100 — его снятие не двигает концовку
    assert all(g["action"] != "grab_cash" for g in res["gates"])


def test_blame_is_deterministic():
    a = blame(copy.deepcopy(WORLD), "escape_rich", **PARAMS)
    b = blame(copy.deepcopy(WORLD), "escape_rich", **PARAMS)
    assert a == b
    assert json.loads(json.dumps(a)) == a


def test_gates_inventory():
    gs = gates(WORLD)
    # 3 действия (pre у sneak_out пуст) + 1 триггер
    assert len(gs) == 2 + 0 + 1
    kinds = {g[0] for g in gs}
    assert kinds == {"action", "trigger"}


def test_endings_universe_includes_declared_even_unreached():
    seen = endings_universe(copy.deepcopy(WORLD), trials=10, depth=5, seed0=1)
    assert {"escape_rich", "escape_poor"} <= set(seen)


def test_report_renders_a_ranking():
    res = blame(copy.deepcopy(WORLD), "escape_rich", **PARAMS)
    text = report(res)
    assert text.startswith("blame:")
    assert "#1" in text and "without:" in text


def test_empty_attribution_message():
    # концовка, которая никем не блокируется гейтом: blame даёт внятный отчёт, не пустоту
    res = blame(copy.deepcopy(WORLD), "escape_poor", **PARAMS)
    assert res["base_rate"] > 0.3
    if not res["gates"]:
        assert "structural" in report(res)


def test_relax_leaves_the_rest_of_the_world_intact():
    from sintgame.blame import _relax
    d = _relax(copy.deepcopy(WORLD), "action", 1, 0)  # action escape, pre[0]
    assert d["actions"][1]["pre"] == []
    assert d["actions"][0]["pre"] == [["ge", "player.gold", 100]]
    assert d["triggers"][0]["pre"] == [["flag", "rich"]]
    assert WORLD["actions"][1]["pre"], "исходный мир не мутирован"
