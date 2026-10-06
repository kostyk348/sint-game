"""LLM-frontend на богатую IR: link -> compile -> validate -> prove (без LLM)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.compile_ir import compile_ir  # noqa: E402
from sintgame.ir import link  # noqa: E402

GOOD = {
    "title": "t", "tone": "n", "seed": 1,
    "entities": {"player": {"type": "actor", "tags": ["player"], "attrs": {"hp": 10, "gold": 0}}},
    "holds": [], "relations": [], "flags": {},
    "actions": [
        {"id": "take", "label": "взять", "pre": [], "eff": [["flag", "key", 1]]},
        {"id": "open", "label": "открыть", "pre": [["flag", "m_door_open"]], "eff": [["end", "open_ok"]]},
    ],
    "machines": {"door": {"initial": "locked", "regions": ["locked", "open"],
                          "transitions": [{"from": "locked", "to": "open", "pre": [["flag", "key"]]}]}},
    "time": {"carrier": "player", "cooldowns": {"day": 5},
             "periodic": [{"cd": "day", "eff": [["add", "player.gold", 1]]}]},
    "constraints": {"vital": ["player"], "min_hp": 1},
}


def _stub(spec):
    return lambda prompt: spec


def test_compile_ir_accepts_good_spec():
    world, report = compile_ir("...", generator=_stub(GOOD))
    assert world is not None, report
    assert "player" in world["entities"]
    proof = report.get("proof") or {}
    assert proof.get("proven_unreachable") == []
    assert proof.get("invariant_may_violate") is False


def test_compile_ir_rejects_proven_unreachable():
    bad = dict(GOOD)
    bad["actions"] = [{"id": "idle", "label": "i", "pre": [], "eff": [["say", "..."]]},
                      {"id": "win", "label": "w", "pre": [["flag", "never"]], "eff": [["end", "win"]]}]
    bad["machines"] = {}
    bad["flags"] = {"never": 0}   # объявлен, но нигде не выставляется
    world, errs = compile_ir("...", rounds=1, generator=_stub(bad))
    assert world is None
    assert any("unreachable" in e for e in errs["errors"]), errs


def test_link_catches_bad_machine_region():
    spec = {"entities": {"player": {"type": "actor", "tags": ["player"], "attrs": {"hp": 10}}},
            "actions": [], "flags": {},
            "machines": {"m": {"initial": "a", "regions": ["a"],
                               "transitions": [{"from": "a", "to": "zzz"}]}}}
    errs = link(spec)
    assert any("zzz" in e for e in errs), errs


if __name__ == "__main__":
    for fn in [test_compile_ir_accepts_good_spec, test_compile_ir_rejects_proven_unreachable,
               test_link_catches_bad_machine_region]:
        fn()
        print("ok", fn.__name__)
