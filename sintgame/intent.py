#!/usr/bin/env python3
"""intent.py — free human text -> intent -> resolve -> (gate) propose + admit.

"Понимает любой текст" — да. "Переподставляет правила в рантайме" — только через
ВОРОТА: любой новый эффект проходит schema-валидацию, проверку границ и запрет на
новые концовки, и только потом попадает в мир. Каждое изменение состояния всё равно
идёт через детерминированное ядро.

Два разных слоя (не путать):
  - ОПИСАНИЯ / ПРОЗА : свободно, LLM пишет что угодно, состояния не касается.
  - ПРАВИЛА / JSON   : только через ворота + ядро.
"""
import hashlib
import json

from . import prompt as P
from .cache import path as _cache_path
from .gen import gen_json
from .schema import SCHEMA_TEXT, _check_cond, _check_eff

INTENT_CACHE = _cache_path("intent_cache.json")

MAX_DELTA = 40  # граница на любой числовой дельта-эффект в рантайме


def _load(path):
    try:
        return json.load(open(path))
    except Exception:
        return {}


def _save(path, obj):
    json.dump(obj, open(path, "w"), ensure_ascii=False, indent=2)


def parse_intent(free, world, w):
    menu = "\n".join(f'- {a["id"]}: {a["label"]}' for a in w.available())
    suffix = (
        "ЗАДАЧА: разбери намерение игрока в текстовой RPG. Верни СТРОГО JSON:\n"
        '{"verb":"что делает","target":"<id или null>","manner":"интонация",'
        '"changes_state":true|false,"known_action":"<id из списка или null>"}\n'
        f"Известные действия:\n{menu}\n"
        f"Состояние игрока: {w.status()}\n"
        f'Игрок пишет: "{free}"\n'
        "known_action — только при точном совпадении смысла. Только JSON."
    )
    obj, _ = gen_json(P.build(P.world_bible(world), suffix))
    return obj or {}


def resolve(intent, w):
    ids = [a["id"] for a in w.available()]
    ka = intent.get("known_action")
    return ka if ka in ids else None


def propose_action(free, intent, world, w):
    ents = ", ".join(world["entities"].keys())
    suffix = (
        "ЗАДАЧА: составь ОДНО новое игровое действие, реализующее намерение.\n"
        "Верни СТРОГО JSON одного действия: {\"id\":str,\"label\":str,\"pre\":[COND],\"eff\":[EFF]}\n"
        f"Сущности (только эти id): {ents}\n"
        "Разрешённые EFF: [\"set\",\"<id>.<attr>\",v] [\"add\",\"<id>.<attr>\",n] [\"flag\",name,0|1] "
        "[\"give\"|\"take\",\"<holder>\",\"<item>\"] [\"dmg\"|\"heal\",\"<id>\",n] [\"rel\",a,b,type,n] [\"say\",\"текст\"]\n"
        f"ЗАПРЕЩЕНО: [\"end\",...]; |n| > {MAX_DELTA}; любые id вне списка.\n"
        "pre — список условий (может быть []). eff — минимум один, реально меняет состояние под намерение.\n"
        f"Намерение: {json.dumps(intent, ensure_ascii=False)}\n"
        f'Реплика игрока: "{free}"\n'
        "Только JSON одного действия."
    )
    obj, _ = gen_json(P.build(P.world_bible(world), suffix))
    return obj


def gate(action, world, w):
    errs = []
    if not isinstance(action, dict):
        return ["не объект"]
    for k in ("id", "label"):
        if k not in action:
            errs.append(f"нет поля {k}")
    if not action.get("eff"):
        errs.append("нет эффектов")
    ents = set(world["entities"])
    for c in action.get("pre", []) or []:
        _check_cond(c, ents, errs, "proposed pre")
    for x in action.get("eff", []) or []:
        _check_eff(x, ents, errs, "proposed eff")
        if x and x[0] == "end":
            errs.append("рантайм-действие не может создавать концовку")
        if x and x[0] in ("add", "dmg", "heal") and isinstance(x[2], (int, float)):
            if abs(x[2]) > MAX_DELTA:
                errs.append(f"дельта за границей {MAX_DELTA}: {x}")
    if action.get("id") in [a["id"] for a in world.get("actions", [])]:
        errs.append("id уже существует")
    # выполнимо ли сейчас
    if not errs:
        try:
            if not all(w.cond(c) for c in action.get("pre", []) or []):
                errs.append("действие невозможно в текущем состоянии (pre ложен)")
        except Exception as ex:
            errs.append(f"pre не вычисляется: {ex}")
    # авторские инварианты: сухой прогон на копии мира
    cons = (world.get("constraints") or {})
    if not errs and cons.get("vital"):
        import copy
        from .kernel import World
        try:
            tmp = copy.deepcopy(world)
            tmp.setdefault("actions", []).append(action)
            tw = World(tmp)
            tw.act(action["id"])
            min_hp = cons.get("min_hp", 1)
            for vid in cons["vital"]:
                hp = tw.get(f"{vid}.hp")
                if hp < min_hp:
                    errs.append(f"инвариант нарушен: {vid}.hp={hp} < {min_hp}")
                if tw.flags.get(f"{vid}_dead"):
                    errs.append(f"инвариант нарушен: {vid} помечен мёртвым")
        except Exception as ex:
            errs.append(f"сухой прогон не удался: {ex}")
    return errs


def _world_hash(world):
    import hashlib
    sig = "|".join([str(world.get("title")), str(world.get("seed")),
                    ",".join(sorted(world.get("entities", {}))),
                    ",".join(sorted(a["id"] for a in world.get("actions", [])))])
    return hashlib.sha1(sig.encode()).hexdigest()[:12]


def pipeline(free, world, w):
    """-> (action_id|None, note, admitted_action|None)"""
    cache = _load(INTENT_CACHE)
    key = hashlib.sha1((_world_hash(world) + "|" + free.strip().lower()).encode()).hexdigest()[:16]
    # cache hit is only honoured if the action still EXISTS and is AVAILABLE now
    if key in cache and cache[key].get("action_id"):
        aid = cache[key]["action_id"]
        if w.can(aid):
            return aid, "cached-intent", None
        # stale (world edited or state changed) -> recompute below
    else:
        aid = None

    intent = parse_intent(free, world, w)
    aid = resolve(intent, w)
    if aid:
        cache[key] = {"action_id": aid, "how": "resolved", "intent": intent}
        _save(INTENT_CACHE, cache)
        return aid, "resolved", None

    cand = propose_action(free, intent, world, w)
    if not isinstance(cand, dict):
        return None, "AGENT-FAILED: агент не вернул JSON действия", None
    errs = gate(cand, world, w)
    if errs:
        return None, "GATE-REJECTED: " + "; ".join(errs[:6]), None

    world.setdefault("actions", []).append(cand)  # w.d is world -> live
    cache[key] = {"action_id": cand["id"], "how": "admitted", "intent": intent, "action": cand}
    _save(INTENT_CACHE, cache)
    return cand["id"], f"ADMITTED new action '{cand['id']}'", cand
