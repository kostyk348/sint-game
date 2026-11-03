#!/usr/bin/env python3
"""blame.py — counterfactual gate attribution: WHICH gates block an ending?

`balance` reports the ending distribution; `tune` adjusts numbers blindly
against an objective. Neither answers the designer's actual question: "why
does nobody reach ending X?" blame does it causally:

  for every GATE (one precondition of one action/trigger) the world is relaxed
  by exactly that gate and re-simulated on the SAME seeds (common random
  numbers, so the comparison is paired, not noisy); the gate's effect is the
  change in the ending's reach rate.

The output is a ranked list: remove gate G -> ending X goes from 2% to 40%.
That is measurement, not guesswork, and it is deterministic end to end.

Cost: gates x trials playouts. For a typical world (~15 gates, 300 playouts
x 120 turns) that is a few seconds of pure Python; the seeds pair the runs,
so even small trial counts give stable rankings.
"""
import copy
import random

from .kernel import World


def _outcome(data, seed, depth):
    """One playout under the random policy; returns (ending_or_None, reason)."""
    w = World(copy.deepcopy(data), seed=seed)
    rng = random.Random(seed)
    for _ in range(depth):
        if w.ended:
            return w.ended, "ended"
        acts = w.available()
        if not acts:
            return None, "dead_end"
        w.act(rng.choice(acts)["id"])
        if w.hit_guard:
            return None, "unstable"
    return w.ended, "no_ending"


def _hist(data, trials, depth, seed0):
    """Outcome histogram under the random policy: endings + failure reasons."""
    hist = {}
    for t in range(trials):
        ending, reason = _outcome(data, seed0 + t, depth)
        key = ending if ending else reason
        hist[key] = hist.get(key, 0) + 1
    return hist


def gates(data):
    """Every gate as (kind, container_index, pre_index, cond) — one precondition
    of one action or trigger."""
    out = []
    for ai, a in enumerate(data.get("actions", [])):
        for i, c in enumerate(a.get("pre", [])):
            out.append(("action", ai, i, a.get("id"), c))
    for ti, t in enumerate(data.get("triggers", [])):
        for i, c in enumerate(t.get("pre", [])):
            out.append(("trigger", ti, i, None, c))
    return out


def _relax(data, kind, ci, pi):
    """The world with exactly that one gate removed (deep copy)."""
    d = copy.deepcopy(data)
    del d["actions" if kind == "action" else "triggers"][ci]["pre"][pi]
    return d


def gate_label(kind, aid, cond):
    import json
    owner = f"action {aid}" if kind == "action" else "trigger"
    return f"{owner}.pre  {json.dumps(cond, ensure_ascii=False)}"


def blame(data, ending, trials=300, depth=120, seed0=1000, top=8, min_gain=0.005):
    """Rank gates by how much removing each one raises `ending`'s reach rate.

    Same seed per playout across all relaxed worlds (paired comparison).
    Deterministic: same world + parameters -> same ranking, byte for byte.
    """
    base = _hist(data, trials, depth, seed0)
    base_rate = base.get(ending, 0) / trials
    gs = gates(data)
    results = []
    for kind, ci, pi, aid, cond in gs:
        h = _hist(_relax(data, kind, ci, pi), trials, depth, seed0)
        rate = h.get(ending, 0) / trials
        gain = rate - base_rate
        if gain >= min_gain:
            results.append({
                "gate": gate_label(kind, aid, cond),
                "kind": kind,
                "action": aid,
                "cond": cond,
                "rate_after": round(rate, 4),
                "gain": round(gain, 4),
            })
    results.sort(key=lambda r: (-r["gain"], r["gate"]))
    return {
        "ending": ending,
        "trials": trials,
        "depth": depth,
        "gates_tested": len(gs),
        "base_rate": round(base_rate, 4),
        "gates": results[:top],
    }


def endings_universe(data, trials, depth, seed0):
    """Every ending id observed across the base playouts plus the world's own
    ["end", ...] effects (so --all can target endings random policy never hits)."""
    seen = set(_hist(data, trials, depth, seed0))
    for a in data.get("actions", []):
        for x in a.get("eff", []):
            if isinstance(x, list) and x and x[0] == "end":
                seen.add(x[1])
    for t in data.get("triggers", []):
        for x in t.get("eff", []):
            if isinstance(x, list) and x and x[0] == "end":
                seen.add(x[1])
    return sorted(seen)


def report(res):
    """Human-readable blame table."""
    lines = [f"blame: ending {res['ending']!r} reached in {res['base_rate']:.1%} "
             f"of {res['trials']} trials ({res['gates_tested']} gates tested)"]
    if not res["gates"]:
        lines.append("  no single gate removal raises this ending — the block "
                     "is structural (try more playouts or check the ending's trigger)")
    for i, g in enumerate(res["gates"], 1):
        lines.append(f"  #{i} +{g['gain']:.1%} -> {g['rate_after']:.1%}  "
                     f"without: {g['gate']}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys
    d = json.load(open(sys.argv[1]))
    res = blame(d, sys.argv[2])
    print(report(res))
    print(json.dumps(res, ensure_ascii=False))
