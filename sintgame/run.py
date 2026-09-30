#!/usr/bin/env python3
"""run.py — «полноценный прогон»: N ходов с проверкой инвариантов и метрик.

Если мир заканчивается, запускается новый эпизод (новый seed) — так набирается N ходов
и проверяется устойчивость на длинной дистанции. Политики: random / explore / greedy.
Проверяются тупики, нестабильные каскады и нарушение авторских инвариантов
(`constraints.vital`).
"""
import copy
import random

from .kernel import World

POLICIES = ("random", "explore", "greedy")


def _choose(policy, acts, rng, used):
    if policy == "random":
        return rng.choice(acts)
    if policy == "explore":
        fresh = [a for a in acts if a["id"] not in used]
        return rng.choice(fresh or acts)

    def weight(a):
        return sum(1 for e in a.get("eff", []) if e and e[0] != "say")
    return max(acts, key=weight)


def soak(data, turns=60, policy="explore", seed=0, check_constraints=True, max_episodes=200):
    if policy not in POLICIES:
        raise ValueError(f"unknown policy: {policy}")
    cons = data.get("constraints") or {}
    vital, min_hp = cons.get("vital", []), cons.get("min_hp", 1)
    all_ids = {a["id"] for a in data.get("actions", [])}
    total, episodes = 0, 0
    endings, violations = {}, []
    used_union = set()
    while total < turns and episodes < max_episodes:
        w = World(copy.deepcopy(data), seed=seed + episodes)
        rng = random.Random(seed + episodes)
        used = set()
        for t in range(turns - total):
            if w.ended:
                break
            acts = w.available()
            if not acts:
                violations.append(f"ep{episodes} turn{t}: dead-end (нет действий)")
                break
            a = _choose(policy, acts, rng, used)
            used.add(a["id"])
            w.act(a["id"])
            total += 1
            if w.hit_guard:
                violations.append(f"ep{episodes} turn{t}: нестабильный каскад триггеров")
            if check_constraints and not w.ended:
                for v in vital:
                    if w.get(f"{v}.hp") < min_hp:
                        violations.append(f"ep{episodes} turn{t}: vital '{v}' ниже min_hp")
        episodes += 1
        used_union |= used
        if w.ended:
            endings[w.ended] = endings.get(w.ended, 0) + 1
        elif total < turns:
            break  # мир не завершился и ходы кончились — дальше смысла нет
    return {"turns": total, "episodes": episodes, "endings": endings,
            "violations": violations, "unused_actions": sorted(all_ids - used_union),
            "policy": policy, "seed": seed}


def report(data, turns=60, policy="explore", seed=0):
    r = soak(data, turns=turns, policy=policy, seed=seed)
    lines = [f"soak: {r['turns']} turns across {r['episodes']} episodes "
             f"(policy={r['policy']}, seed={r['seed']})",
             f"  endings: {r['endings'] or '—'}",
             f"  violations: {len(r['violations'])}"]
    for v in r["violations"][:10]:
        lines.append(f"    ! {v}")
    lines.append(f"  unused actions: {r['unused_actions']}")
    return "\n".join(lines), r
