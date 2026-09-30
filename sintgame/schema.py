#!/usr/bin/env python3
"""Schema text + invariant validator + reachability simulator for world.json."""
import copy
import random

from .kernel import World

SCHEMA_TEXT = """
WOLRD JSON:
{
  "schema": 1,
  "title": str,
  "tone": str,
  "seed": int,
  "entities": { "<id>": {"type":str, "tags":[str], "attrs":{ "<name>": number }, "desc": str, "voice": str} },
  "holds":    [ ["<holder_id>", "<item_id>"], ... ],
  "relations":[ ["<from_id>","<to_id>","<type>", number], ... ],
  "flags":    { "<name>": 0|1 },
  "actions":  [ {"id":str, "label":str, "pre":[COND], "eff":[EFF]} ],
  "triggers": [ {"pre":[COND], "eff":[EFF], "once":bool} ],
  "constraints": { "vital": [str], "min_hp": number }
}
constraints.vital = id персонажей, которые НЕ должны погибать (инвариант, который
                     проверяют ворота на любом рантайм-действии).
COND (list, AND): ["flag",name] ["not",COND] ["gt"|"lt"|"ge"|"le"|"eq","<id>.<attr>"|<flag>,num]
                   ["has","<holder>","<item>"] ["rel_gt"|"rel_lt","<from>","<to>","<type>",num]
EFF  (list):       ["set","<id>.<attr>"|<flag>,val] ["add","<id>.<attr>",num] ["flag",name,0|1]
                   ["give"|"take","<holder>","<item>"] ["dmg"|"heal","<id>",num|{"roll":"1d6","plus":"<id>.<attr>"}]
                   ["rel","<from>","<to>","<type>",num] ["say","text"] ["end","<ending_id>"]
""".replace("WOLRD", "WORLD")


def _path_ids(p):
    return [p.split(".", 1)[0]] if "." in p else []


def _check_cond(c, ents, errs, ctx):
    if not isinstance(c, list) or not c:
        errs.append(f"{ctx}: bad COND {c}")
        return
    op = c[0]
    if op == "flag":
        return
    if op == "not":
        _check_cond(c[1], ents, errs, ctx)
    elif op in ("gt", "lt", "ge", "le", "eq"):
        for i in _path_ids(c[1]):
            if i not in ents:
                errs.append(f"{ctx}: unknown entity '{i}' in {c}")
    elif op == "has":
        for i in (c[1], c[2]):
            if i not in ents:
                errs.append(f"{ctx}: unknown entity '{i}' in {c}")
    elif op in ("rel_gt", "rel_lt"):
        for i in (c[1], c[2]):
            if i not in ents:
                errs.append(f"{ctx}: unknown entity '{i}' in {c}")
    else:
        errs.append(f"{ctx}: unknown COND op '{op}'")


def _check_eff(x, ents, errs, ctx):
    if not isinstance(x, list) or not x:
        errs.append(f"{ctx}: bad EFF {x}")
        return
    op = x[0]
    if op in ("set", "add"):
        for i in _path_ids(x[1]):
            if i not in ents:
                errs.append(f"{ctx}: unknown entity '{i}' in {x}")
    elif op == "flag":
        return
    elif op in ("give", "take", "dmg", "heal"):
        i = x[1] if op in ("dmg", "heal") else x[1]
        if i not in ents:
            errs.append(f"{ctx}: unknown entity '{i}' in {x}")
        if op in ("give", "take") and x[2] not in ents:
            errs.append(f"{ctx}: unknown item '{x[2]}' in {x}")
    elif op == "rel":
        for i in (x[1], x[2]):
            if i not in ents:
                errs.append(f"{ctx}: unknown entity '{i}' in {x}")
    elif op in ("say", "end"):
        return
    else:
        errs.append(f"{ctx}: unknown EFF op '{op}'")


def validate(data):
    errs = []
    if not isinstance(data, dict):
        return ["root is not an object"]
    ents = set(data.get("entities", {}) or {})
    if "player" not in ents:
        errs.append("no entity with id 'player'")
    cons = data.get("constraints", {}) or {}
    for vid in cons.get("vital", []) or []:
        if vid not in ents:
            errs.append(f"constraints.vital: unknown entity '{vid}'")
    if not data.get("actions"):
        errs.append("no actions")
    for a in data.get("actions", []) or []:
        for k in ("id", "label"):
            if k not in a:
                errs.append(f"action missing '{k}': {a}")
        if not a.get("eff"):
            errs.append(f"action {a.get('id')} has no effects")
        for c in a.get("pre", []) or []:
            _check_cond(c, ents, errs, f"action {a.get('id')} pre")
        for x in a.get("eff", []) or []:
            _check_eff(x, ents, errs, f"action {a.get('id')} eff")
    for t in data.get("triggers", []) or []:
        for c in t.get("pre", []) or []:
            _check_cond(c, ents, errs, "trigger pre")
        for x in t.get("eff", []) or []:
            _check_eff(x, ents, errs, "trigger eff")
    # start must have at least one available action
    try:
        w = World(copy.deepcopy(data), seed=1)
        if not w.available():
            errs.append("no action available at start")
    except Exception as ex:
        errs.append(f"kernel rejected world: {ex}")
    return errs


def simulate(data, trials=300, depth=120, seed0=1000):
    """Случайные прогоны: концовки, тупики, нестабильность, средняя длина партии."""
    reached, dead_ends, unstable, no_end = {}, 0, 0, 0
    lengths = []
    for t in range(trials):
        w = World(copy.deepcopy(data), seed=seed0 + t)
        rng = random.Random(seed0 + t)
        step = 0
        for step in range(depth):
            if w.ended:
                break
            acts = w.available()
            if not acts:
                dead_ends += 1
                break
            w.act(rng.choice(acts)["id"])
            if w.hit_guard:
                unstable += 1
                break
        if w.ended:
            reached[w.ended] = reached.get(w.ended, 0) + 1
            lengths.append(step + 1)
        else:
            no_end += 1
    return {"endings_reached": reached, "dead_ends": dead_ends,
            "unstable": unstable, "no_ending": no_end, "trials": trials,
            "avg_turns": round(sum(lengths) / len(lengths), 1) if lengths else 0}


if __name__ == "__main__":
    import json
    import sys
    d = json.load(open(sys.argv[1]))
    e = validate(d)
    print("VALIDATOR:", "OK" if not e else f"{len(e)} error(s)")
    for x in e:
        print("  -", x)
    if not e:
        print("SIMULATION:", json.dumps(simulate(d), ensure_ascii=False))
