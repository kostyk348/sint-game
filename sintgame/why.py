#!/usr/bin/env python3
"""why.py — self-explaining gates: WHY is an action unavailable right now?

The kernel refuses an action with a bare "unavailable"; the LLM intent layer (or
a human designer) then guesses. `why_unavailable` evaluates every precondition
of the action against the live state and reports each one's verdict with the
actual value: which gate blocks, how far it is from passing. That turns
"unavailable" into an actionable diagnosis the caller can react to (and the
prose layer can narrate).

Deterministic: same world + save/seed -> same answer. No LLM anywhere.
"""
from .kernel import World

import copy


def cond_label(c):
    """Human-readable one-line form of a COND (list op-args)."""
    if not isinstance(c, list) or not c:
        return repr(c)
    op = c[0]
    if op == "flag":
        return f"flag {c[1]}"
    if op == "not":
        return f"not ({cond_label(c[1])})"
    if op in ("gt", "lt", "ge", "le", "eq"):
        sym = {"gt": ">", "lt": "<", "ge": ">=", "le": "<=", "eq": "=="}[op]
        return f"{c[1]} {sym} {c[2]}"
    if op == "has":
        return f"{c[1]} has {c[2]}"
    if op in ("rel_gt", "rel_lt"):
        sym = ">" if op == "rel_gt" else "<"
        return f"rel {c[1]}->{c[2]} [{c[3]}] {sym} {c[4]}"
    return repr(c)


def _cond_detail(w, c):
    """Machine-readable detail: the actual value behind the verdict."""
    op = c[0] if isinstance(c, list) and c else "?"
    if op in ("gt", "lt", "ge", "le", "eq"):
        return {"kind": "value", "path": c[1], "actual": w.get(c[1]), "threshold": c[2]}
    if op == "flag":
        return {"kind": "flag", "flag": c[1], "actual": w.flags.get(c[1], 0)}
    if op == "has":
        return {"kind": "holds", "holder": c[1], "item": c[2],
                "actual": (c[1], c[2]) in w.holds}
    if op in ("rel_gt", "rel_lt"):
        return {"kind": "relation", "from": c[1], "to": c[2], "type": c[3],
                "actual": w.rel.get((c[1], c[2], c[3]), 0), "threshold": c[4]}
    if op == "not":
        return {"kind": "not", "inner": _cond_detail(w, c[1]), "actual": w.cond(c)}
    return {"kind": op}


def why_unavailable(data, aid, seed=None, save=None):
    """Evaluate every precondition of action `aid` against the live state.

    `save` (a state() dict) pins the state exactly; otherwise the world is
    created with `seed`. Returns a dict: action identity, per-cond verdicts
    with actual values, and the blocking subset.
    """
    a = next((x for x in data.get("actions", []) if x.get("id") == aid), None)
    if a is None:
        return {"action": aid, "exists": False}
    w = World(copy.deepcopy(data))
    if save is not None:
        w.restore(copy.deepcopy(save))
    elif seed is not None:
        w = World(copy.deepcopy(data), seed=seed)
    rows = []
    for i, c in enumerate(a.get("pre", [])):
        ok = bool(w.cond(c))
        rows.append({"index": i, "cond": cond_label(c), "ok": ok,
                     "detail": _cond_detail(w, c)})
    blocking = [r for r in rows if not r["ok"]]
    return {
        "action": aid,
        "label": a.get("label", ""),
        "exists": True,
        "available": not blocking,
        "conds": rows,
        "blocking": blocking,
    }


def report(res):
    """Human-readable verdict table for one why_unavailable result."""
    if not res.get("exists"):
        return f"why: no such action {res['action']!r}"
    status = "available" if res["available"] else "UNAVAILABLE"
    lines = [f"why: {res['action']} ({res['label']}) — {status}"]
    for r in res["conds"]:
        mark = "✓" if r["ok"] else "✗"
        d = r["detail"]
        extra = ""
        if d["kind"] == "value":
            extra = f"  (current: {d['actual']})"
        elif d["kind"] == "flag":
            extra = f"  (current: {d['actual']})"
        elif d["kind"] == "holds":
            extra = "  (held)" if d["actual"] else "  (not held)"
        elif d["kind"] == "relation":
            extra = f"  (current: {d['actual']})"
        elif d["kind"] == "not":
            extra = f"  (inner: {d['actual']})"
        lines.append(f"  {mark} {r['cond']}{extra}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys
    d = json.load(open(sys.argv[1]))
    res = why_unavailable(d, sys.argv[2])
    print(report(res))
    print(json.dumps(res, ensure_ascii=False))
