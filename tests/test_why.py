"""why.py — самообъясняющие гейты: вердикты по каждому условию с фактическими значениями."""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.kernel import World  # noqa: E402
from sintgame.why import cond_label, report, why_unavailable  # noqa: E402

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
    "triggers": [],
}


def test_unavailable_reports_actual_value():
    res = why_unavailable(copy.deepcopy(WORLD), "escape")
    assert res["exists"] and not res["available"]
    assert res["blocking"][0]["cond"] == "player.gold >= 500"
    assert res["blocking"][0]["detail"]["actual"] == 100
    ok = [r for r in res["conds"] if r["ok"]]
    assert not ok, "единственный pre должен блокировать"


def test_save_pins_the_state_exactly():
    w = World(copy.deepcopy(WORLD))
    w.act("grab_cash")
    w.act("grab_cash")
    save = w.state()
    res = why_unavailable(copy.deepcopy(WORLD), "escape", save=save)
    assert res["available"], "gold=500 после двух act -> гейт пройден"


def test_available_action_has_no_blocking():
    res = why_unavailable(copy.deepcopy(WORLD), "grab_cash")
    assert res["exists"] and res["available"] and res["blocking"] == []


def test_missing_action():
    res = why_unavailable(copy.deepcopy(WORLD), "nope")
    assert res["exists"] is False


def test_cond_label_forms():
    assert cond_label(["ge", "player.gold", 500]) == "player.gold >= 500"
    assert cond_label(["flag", "rich"]) == "flag rich"
    assert cond_label(["has", "player", "key"]) == "player has key"
    assert cond_label(["rel_gt", "a", "b", "trust", 3]) == "rel a->b [trust] > 3"
    assert cond_label(["not", ["flag", "x"]]) == "not (flag x)"
    assert cond_label(["eq", "day.time", 12]) == "day.time == 12"


def test_report_is_human_readable():
    res = why_unavailable(copy.deepcopy(WORLD), "escape")
    text = report(res)
    assert "UNAVAILABLE" in text
    assert "✗" in text and "(current: 100)" in text
    res2 = why_unavailable(copy.deepcopy(WORLD), "sneak_out")
    assert "available" in report(res2)
    assert "no such action" in report({"action": "x", "exists": False})


def test_json_roundtrip():
    res = why_unavailable(copy.deepcopy(WORLD), "escape")
    res2 = json.loads(json.dumps(res))
    assert res2 == res
