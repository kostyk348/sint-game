#!/usr/bin/env python3
"""tune.py — авто-тюнинг чисел мира под баланс концовок (чёрный ящик + симуляция).

Собирает числовые константы (значения эффектов и пороги условий), затем hill-climb:
мутирует их в границах и принимает изменение, если симуляция стала ближе к балансу
(ниже доля доминирующей концовки, все концовки достижимы, меньше тупиков).
Детерминирован заданным seed.
"""
import copy
import random

from .schema import simulate
from .search import declared_endings


def _get(data, path):
    cur = data
    for p in path.strip("/").split("/"):
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    return cur


def _set(data, path, val):
    cur = data
    parts = path.strip("/").split("/")
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    last = parts[-1]
    if isinstance(cur, list):
        cur[int(last)] = val
    else:
        cur[last] = val


def collect_params(data):
    params = []

    def add(path, v, lo, hi):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            params.append({"path": path, "value": v, "lo": lo, "hi": hi})

    def scan_pre(c, base):
        if not isinstance(c, list) or not c:
            return
        if c[0] == "not":
            scan_pre(c[1], base)
        elif c[0] in ("gt", "lt", "ge", "le", "eq") and len(c) >= 3:
            add(base + "/2", c[2], 0, 300)

    def scan_eff(e, base):
        if not isinstance(e, list) or not e:
            return
        if e[0] in ("add", "set") and len(e) >= 3:
            add(base + "/2", e[2], -60, 60)
        elif e[0] in ("dmg", "heal") and len(e) >= 3:
            add(base + "/2", e[2], 0, 60)

    for i, a in enumerate(data.get("actions", [])):
        for j, c in enumerate(a.get("pre", []) or []):
            scan_pre(c, f"/actions/{i}/pre/{j}")
        for j, e in enumerate(a.get("eff", []) or []):
            scan_eff(e, f"/actions/{i}/eff/{j}")
    for i, t in enumerate(data.get("triggers", []) or []):
        for j, c in enumerate(t.get("pre", []) or []):
            scan_pre(c, f"/triggers/{i}/pre/{j}")
        for j, e in enumerate(t.get("eff", []) or []):
            scan_eff(e, f"/triggers/{i}/eff/{j}")
    return params


def objective(sim, n_endings, target_max=0.6):
    dist = sim["endings_reached"]
    total = sum(dist.values()) or 1
    maxfrac = (max(dist.values()) / total) if dist else 1.0
    unreached = max(0, n_endings - len(dist))
    dome = max(0.0, maxfrac - target_max)
    return round(dome * 2 + 0.2 * unreached + 0.05 * (sim["dead_ends"] / max(1, sim["trials"])), 4)


def tune(data, trials=300, iters=80, seed=0, target_max=0.6):
    n_end = len(declared_endings(data))
    params = collect_params(data)
    if not params:
        return copy.deepcopy(data), {"before": 0.0, "after": 0.0, "improved": False, "note": "нет числовых параметров"}

    def ev(d):
        return objective(simulate(d, trials=trials, seed0=1000 + seed), n_end, target_max)

    best = copy.deepcopy(data)
    best_obj = before = ev(best)
    rng = random.Random(seed)
    for _ in range(iters):
        cand = copy.deepcopy(best)
        for _ in range(rng.randint(1, 2)):
            p = rng.choice(params)
            cur = _get(best, p["path"])
            if not isinstance(cur, (int, float)):
                continue
            nv = max(p["lo"], min(p["hi"], cur + rng.choice([-1, 1])))
            _set(cand, p["path"], nv)
        o = ev(cand)
        if o < best_obj:
            best, best_obj = cand, o
    return best, {"before": before, "after": best_obj, "improved": best_obj < before,
                  "params": len(params), "trials": trials, "iters": iters}
