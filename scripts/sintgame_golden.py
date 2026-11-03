#!/usr/bin/env python3
"""SINT-GAME golden generator: runs the ORIGINAL Python kernel/ir/schema on
the example worlds + a rich IR spec and prints canonical results for the
Rust tests (scripts/sintgame_make_golden_tests.py converts to Rust cases).

Everything is deterministic: seeds fixed, scripted plays always take the
FIRST available action; simulate() uses random.Random(seed) — the Rust port
implements MT19937 bit-exactly, so playouts must match.
"""
import io
import json
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sintgame.kernel import World  # noqa: E402
from sintgame import ir as IR  # noqa: E402
from sintgame.schema import validate, simulate  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLDS = ["campaign", "sandbox", "station", "lighthouse"]

# Богатая спека для IR: иерархические машины + время + агенты
RICH_SPEC = {
    "title": "rich",
    "tone": "neutral",
    "seed": 5,
    "entities": {
        "player": {"type": "actor", "tags": [], "attrs": {"hp": 10, "gold": 5}},
        "gate": {"type": "prop", "tags": [], "attrs": {}},
        "guard": {"type": "actor", "tags": [], "attrs": {"hp": 4}},
        "key": {"type": "item", "tags": [], "attrs": {}},
    },
    "holds": [],
    "relations": [["player", "guard", "trust", 0]],
    "flags": {"has_key": 0},
    "actions": [
        {"id": "wait", "label": "Ждать", "pre": [], "eff": [["say", "ждёт"]]},
        {"id": "bribe", "label": "Дать взятку", "pre": [["gt", "player.gold", 3]],
         "eff": [["add", "player.gold", -3], ["rel", "player", "guard", "trust", 2],
                 ["say", "стража подмазали"]]},
        {"id": "take_key", "label": "Взять ключ", "agent": "player",
         "pre": [["ge", "player.guard".replace("player.", "") + "_trust_dummy", 0]],
         "eff": [["give", "player", "key"], ["flag", "has_key", 1], ["say", "ключ у игрока"]]},
        {"id": "fight", "label": "Драться", "agent": "guard",
         "pre": [], "eff": [["dmg", "guard", {"roll": "2d6"}],
                            ["dmg", "player", {"roll": "1d6", "plus": "guard.hp"}],
                            ["say", "драка"]]},
    ],
    "triggers": [
        {"pre": [["has", "player", "key"], ["flag", "gate_open"]],
         "eff": [["say", "ворота открыты"], ["end", "escaped"]], "once": True},
    ],
    "machines": {
        "gate": {
            "initial": "closed",
            "regions": ["closed", "open"],
            "transitions": [
                {"from": "closed", "to": "open", "pre": [["flag", "has_key"]]},
            ],
            "children": {
                "alarm": {
                    "when": "closed",
                    "initial": "off",
                    "regions": ["off", "on"],
                    "transitions": [
                        {"from": "off", "to": "on", "pre": [["rel_gt", "player", "guard", "trust", 1]]},
                    ],
                }
            },
        }
    },
    "time": {
        "carrier": "player",
        "cooldowns": {"day": 3},
        "periodic": [
            {"cd": "day", "pre": [], "eff": [["say", "новый день"], ["add", "player.gold", 1]]},
        ],
    },
}

# Спека с ошибками линковки
BROKEN_SPEC = {
    "entities": {"player": {"type": "actor", "tags": [], "attrs": {}}},
    "flags": {},
    "actions": [
        {"id": "a", "label": "A", "pre": [["flag", "nope"]],
         "eff": [["dmg", "ghost", 1], ["give", "player", "noitem"]]},
    ],
    "machines": {
        "m": {"initial": "x", "regions": ["a"], "transitions": [{"from": "zz", "to": "a"}]},
    },
}


def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def scripted_trace(world, seed, steps, save_at):
    """Игровая дорожка: всегда первый available; полное состояние на save_at
    и в конце (включая rng); промежуточно — said/ended/status/avail ids."""
    w = World(json.loads(json.dumps(world)), seed=seed)
    trace = []
    saved = None
    for i in range(steps):
        if w.ended:
            break
        acts = w.available()
        if not acts:
            trace.append({"t": i, "dead": True})
            break
        aid = acts[0]["id"]
        said = list(w.act(aid))
        entry = {
            "t": i,
            "act": aid,
            "said": said,
            "ended": w.ended,
            # status() исключён из goldens: порядок ключей attrs — вставной в
            # Python dict, алфавитный в Rust BTreeMap (косметика CLI, не семантика)
            "snap": canonical(w.snapshot()),
            "avail": [a["id"] for a in w.available()],
        }
        if i == save_at:
            saved = w.state()
            entry["saved_state"] = canonical(saved)
        trace.append(entry)
    out = {"trace": trace, "final_state": canonical(w.state())}
    if saved is not None:
        # restore в свежий мир должен дать то же состояние, что на момент сейва
        w2 = World(json.loads(json.dumps(world)), seed=seed)
        w2.restore(saved)
        out["restored_state"] = canonical(w2.state())
    return out


def main():
    out = {}
    for name in WORLDS:
        path = os.path.join(REPO, "examples", name, "world.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        out[f"{name}:validate"] = {"errors": validate(data)}
        out[f"{name}:simulate"] = canonical(simulate(data, trials=50, depth=40, seed0=1000))
        out[f"{name}:play"] = canonical(scripted_trace(data, seed=7, steps=25, save_at=10))

    out["rich:compile"] = canonical(IR.compile_game(RICH_SPEC))
    flat = IR.compile_game(RICH_SPEC)
    out["rich:validate_flat"] = {"errors": validate(flat)}
    out["rich:play"] = canonical(scripted_trace(flat, seed=5, steps=20, save_at=8))
    out["rich:link"] = {"errors": IR.link(RICH_SPEC)}
    out["broken:link"] = {"errors": IR.link(BROKEN_SPEC)}

    print(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
