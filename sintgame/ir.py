#!/usr/bin/env python3
"""ir.py — RICH FRONTEND: спека игры -> плоский мир для ядра.

Масштаб компилятора: автор (или LLM) описывает логику БОГАТО (машины состояний,
время/кулдауны, агенты), а компилятор ПОНИЖАЕТ её в простую детерминированную модель
(kernel) — ту же, на которой уже работает звучий анализ (abstract.py).

  { "entities":…, "holds":…, "relations":…, "flags":…,
    "actions":[ …обычные действия… ],
    "machines": { "<id>": { "initial": "<region>", "regions": ["a","b"],
                            "transitions":[ {"from","to","pre":[…],"eff":[…]} ] } },
    "time":  { "carrier":"player", "cooldowns":{"day":30},
               "periodic":[ {"cd":"day","pre":[…],"eff":[…],"once":false} ] },
    "constraints": { "vital":[…], "min_hp":1 } }

ПОНИЖЕНИЕ:
  машина        -> по флагу на регион  m_<id>_<region>; переход = триггер, ставящий флаги;
  время         -> атрибут-кулдаун + скрытое действие __tick__ (уменьшает кулдауны) +
                   периодический триггер, сбрасывающий кулдаун;
  агенты        -> у действия поле "agent" (ядро фильтрует available(actor)).

Ничего из этого не меняет анализ: он читает уже понижённые переходы, поэтому
доказательства (недостижимость/инварианты/liveness) работают для машин и времени
БЕЗ переписывания.
"""


def compile_game(spec):
    world = {
        "schema": 1,
        "title": spec.get("title", "ir"),
        "tone": spec.get("tone", "neutral"),
        "seed": spec.get("seed", 1),
        "entities": _deep(spec.get("entities", {})),
        "holds": [list(h) for h in spec.get("holds", [])],
        "relations": [list(r) for r in spec.get("relations", [])],
        "flags": dict(spec.get("flags", {})),
        "actions": [dict(a) for a in spec.get("actions", [])],
        "triggers": [dict(t) for t in spec.get("triggers", [])],
    }

    # --- машины состояний (иерархия): регион -> флаг, переход -> триггер -----------
    for mid, m in (spec.get("machines") or {}).items():
        _compile_machine(mid, m, world["flags"], world["triggers"], [], "m_")

    # --- время: кулдауны + периодика ---------------------------------------------
    tm = spec.get("time") or {}
    carrier = tm.get("carrier", "player")
    cooldowns = tm.get("cooldowns") or {}
    if cooldowns:
        world["entities"].setdefault(carrier, {"type": "actor", "tags": [], "attrs": {}})
        for cd, period in cooldowns.items():
            world["entities"][carrier].setdefault("attrs", {})[f"cd_{cd}"] = period
        tick_eff = [["add", f"{carrier}.cd_{cd}", -1] for cd in cooldowns.keys()]
        world["actions"].append({"id": "__tick__", "label": "time", "pre": [],
                                 "eff": tick_eff, "hidden": True})
        for p in tm.get("periodic", []):
            cd = p["cd"]
            period = cooldowns.get(cd, 0)
            pre = [["le", f"{carrier}.cd_{cd}", 0]] + list(p.get("pre", []))
            eff = [["set", f"{carrier}.cd_{cd}", period]] + list(p.get("eff", []))
            world["triggers"].append({"pre": pre, "eff": eff, "once": bool(p.get("once", False))})

    if "constraints" in spec:
        world["constraints"] = dict(spec["constraints"])
    return world


def _deep(x):
    import copy
    return copy.deepcopy(x)


# --- иерархические машины + контракты (ссылку на чужие регионы-флаги) ---------------

def _machine_flags(mid, m, prefix=""):
    out = [f"{prefix}{mid}_{r}" for r in m.get("regions", [])]
    for cid, cm in (m.get("children") or {}).items():
        out += _machine_flags(cid, cm, f"{prefix}{mid}_")
    return out


def _compile_machine(mid, m, flags, triggers, guard, prefix):
    regions = m.get("regions", [])
    initial = m.get("initial", regions[0] if regions else "")
    for r in regions:
        flags[f"{prefix}{mid}_{r}"] = 1 if r == initial else 0
    for t in m.get("transitions", []):
        pre = ([["flag", f"{prefix}{mid}_{t['from']}"]] + list(guard)
               + list(t.get("pre", [])))
        eff = ([["flag", f"{prefix}{mid}_{t['from']}", 0], ["flag", f"{prefix}{mid}_{t['to']}", 1]]
               + list(t.get("eff", [])))
        triggers.append({"pre": pre, "eff": eff, "once": bool(t.get("once", False))})
    for cid, cm in (m.get("children") or {}).items():
        when = cm.get("when")
        g2 = list(guard) + ([["flag", f"{prefix}{mid}_{when}"]] if when else [])
        _compile_machine(cid, cm, flags, triggers, g2, f"{prefix}{mid}_")


def _link_machine(mid, m, errs):
    regions = m.get("regions", [])
    init = m.get("initial", regions[0] if regions else "")
    if init not in regions:
        errs.append(f"machine {mid}: initial '{init}' not in regions")
    for t in m.get("transitions", []):
        if t.get("from") not in regions:
            errs.append(f"machine {mid}: transition from '{t.get('from')}' unknown")
        if t.get("to") not in regions:
            errs.append(f"machine {mid}: transition to '{t.get('to')}' unknown")
    for cid, cm in (m.get("children") or {}).items():
        when = cm.get("when")
        if when and when not in regions:
            errs.append(f"machine {mid}: child {cid} when '{when}' unknown")
        _link_machine(cid, cm, errs)


def link(spec):
    """Линковка/тайпчек спеки ДО компиляции: неизвестные сущности и флаги, битые регионы."""
    errs = []
    machines = spec.get("machines") or {}
    for mid, m in machines.items():
        _link_machine(mid, m, errs)
    mflags = set()
    for mid, m in machines.items():
        mflags |= set(_machine_flags(mid, m, "m_"))
    declared = set((spec.get("flags") or {}).keys())
    produced = set()
    items = list(spec.get("actions", []) or []) + list(spec.get("triggers", []) or [])
    for a in items:
        for x in a.get("eff", []) or []:
            if x and x[0] == "flag":
                produced.add(x[1])
            if x and x[0] == "set" and isinstance(x[1], str) and "." not in x[1]:
                produced.add(x[1])
    ents = set((spec.get("entities") or {}).keys())

    def chk_cond(c):
        if not isinstance(c, list) or not c:
            return
        op = c[0]
        if op == "flag":
            if c[1] not in declared | mflags | produced:
                errs.append(f"unknown flag: {c[1]}")
        elif op == "not":
            chk_cond(c[1])
        elif op in ("gt", "lt", "ge", "le", "eq"):
            if isinstance(c[1], str) and "." in c[1] and c[1].split(".")[0] not in ents:
                errs.append(f"unknown entity: {c[1].split('.')[0]}")
        elif op == "has":
            for e in (c[1], c[2]):
                if e not in ents:
                    errs.append(f"unknown entity: {e}")
        elif op in ("rel_gt", "rel_lt"):
            for e in (c[1], c[2]):
                if e not in ents:
                    errs.append(f"unknown entity: {e}")

    def chk_eff(x):
        if not isinstance(x, list) or not x:
            return
        op = x[0]
        if op in ("set", "add") and isinstance(x[1], str) and "." in x[1]:
            if x[1].split(".")[0] not in ents:
                errs.append(f"unknown entity: {x[1].split('.')[0]}")
        elif op in ("give", "take"):
            for e in (x[1], x[2]):
                if e not in ents:
                    errs.append(f"unknown entity: {e}")
        elif op in ("dmg", "heal"):
            if x[1] not in ents:
                errs.append(f"unknown entity: {x[1]}")
        elif op == "rel":
            for e in (x[1], x[2]):
                if e not in ents:
                    errs.append(f"unknown entity: {e}")

    for a in items:
        for c in a.get("pre", []) or []:
            chk_cond(c)
        for x in a.get("eff", []) or []:
            chk_eff(x)
    return errs
