#!/usr/bin/env python3
"""sandbox.py — открытый песочный режим: долгие кампании (500+ шагов) без обязательного финала.

Отличия от `run`:
  - мир может НЕ иметь объявленных концовок — это не ошибка, это сэндбокс;
  - игру не нужно завершать: играем N ходов подряд в одном непрерывном состоянии;
  - ДИРЕКТОР (опционально) каждые K ходов добавляет новое событие/возможность — мир растёт
    по ходу игры. Каждое дополнение проходит ворота: схема + мёртвые предпосылки, и не
    создаёт концовок. Так получается условный сэндбокс в духе Pax Historia: структура
    держит связность, а контент не заканчивается.

`director` инъектируется — логика тестируется без LLM.
"""
import copy
import random

from . import prompt as P
from .content import merge as merge_world
from .content import verify
from .gen import gen_json
from .kernel import World
from .run import _choose


def director_llm(world, state_summary):
    """LLM-директор: придумывает одно новое событие-действие под текущее состояние мира."""
    suffix = (
        "ЗАДАЧА: придумай ОДНО новое событие или возможность в открытом мире (сэндбокс).\n"
        'Верни ТОЛЬКО JSON: {"actions":[{"id":"","label":"","pre":[],"eff":[]}], "triggers":[], "flags":{}}\n'
        "- используй ТОЛЬКО существующие id сущностей;\n"
        '- ЗАПРЕЩЕНО ["end", ...] — мир открытый, без финала;\n'
        "- действие должно быть доступно из текущего состояния (pre выполним сейчас);\n"
        f"- состояние мира: {state_summary}\n"
    )
    return gen_json(P.build(P.world_bible(world), suffix))[0]


def _admit(world, patch):
    """Проверить и вплавить патч директора В ЖИВОЙ мир (in place). Возвращает добавленные id."""
    if not isinstance(patch, dict):
        raise ValueError("director вернул не JSON")
    for a in patch.get("actions", []) or []:
        if any(e and e[0] == "end" for e in a.get("eff", []) or []):
            raise ValueError("директор не может создавать концовки")
    merged = merge_world(world, patch)
    errs = verify(merged, require_endings=False)  # добавления не отнимают концовки
    if errs:
        raise ValueError("; ".join(errs[:3]))
    for k, v in (patch.get("entities") or {}).items():
        world["entities"][k] = v
    world.setdefault("holds", []).extend(patch.get("holds") or [])
    world.setdefault("relations", []).extend(patch.get("relations") or [])
    for a in patch.get("actions") or []:
        world["actions"].append(a)
    world.setdefault("triggers", []).extend(patch.get("triggers") or [])
    for k, v in (patch.get("flags") or {}).items():
        world.setdefault("flags", {}).setdefault(k, v)
    return [a["id"] for a in (patch.get("actions") or [])]


def endurance(data, turns=500, policy="linger", seed=0, director=None, every=0, check_constraints=True):
    world = copy.deepcopy(data)
    w = World(world, seed=seed)
    rng = random.Random(seed)
    used, violations = set(), []
    dead_ends = director_calls = added = 0
    cons = world.get("constraints") or {}
    vital, min_hp = cons.get("vital", []), cons.get("min_hp", 1)
    played = 0
    for t in range(turns):
        if w.ended:
            break
        acts = w.available()
        if not acts:
            dead_ends += 1
            violations.append(f"turn {t}: dead-end (нет доступных действий)")
            break
        a = _choose(policy, acts, rng, used)
        used.add(a["id"])
        w.act(a["id"])
        played += 1
        if w.hit_guard:
            violations.append(f"turn {t}: нестабильный каскад триггеров")
        if check_constraints and not w.ended:
            for v in vital:
                if w.get(f"{v}.hp") < min_hp:
                    violations.append(f"turn {t}: vital '{v}' ниже min_hp")
        if director and every and (t + 1) % every == 0:
            director_calls += 1
            try:
                added += len(_admit(world, director(world, w.status())))
            except Exception as ex:  # noqa: BLE001 — отклонённый контент не должен ломать прогон
                violations.append(f"turn {t}: директор отклонён: {ex}")
    return {"turns": played, "ended": w.ended, "ending": w.ended,
            "dead_ends": dead_ends, "violations": violations,
            "actions_total": len(world.get("actions", [])),
            "actions_added": added, "director_calls": director_calls,
            "distinct_actions_used": len(used), "policy": policy, "seed": seed}


def report(data, turns=500, policy="linger", seed=0, director=None, every=0):
    r = endurance(data, turns=turns, policy=policy, seed=seed, director=director, every=every)
    lines = [f"sandbox: {r['turns']} turns continuous (policy={r['policy']}, seed={r['seed']})",
             f"  ended: {r['ending'] or 'нет (открытый финал)'}",
             f"  distinct actions used: {r['distinct_actions_used']} / {r['actions_total']}",
             f"  dead-ends: {r['dead_ends']}",
             f"  director: {r['director_calls']} calls, +{r['actions_added']} actions",
             f"  violations: {len(r['violations'])}"]
    for v in r["violations"][:10]:
        lines.append(f"    ! {v}")
    return "\n".join(lines), r
