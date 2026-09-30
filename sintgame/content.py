#!/usr/bin/env python3
"""content.py — генерация КОНТЕНТА в существующий мир, под верификацией.

Компилятор (`compile_world`) делает мир целиком. `content` делает НАДСТРОЙКУ против
замороженного скелета: NPC, предметы, локации, квесты. Каждое дополнение проходит
`verify()`:

  1. схема валидна;
  2. нет мёртвых предпосылок (флаг требуется, но нигде не выставляется; предмет
     требуется, но ниоткуда не берётся);
  3. все объявленные концовки по-прежнему достижимы.

Провалившееся дополнение откатывается; можно переделать с подсказкой об ошибках.
`generator` инъектируется, чтобы логика merge+verify тестировалась БЕЗ LLM.
"""
import copy

from . import prompt as P
from .gen import gen_json
from .schema import validate
from .search import dangling_prerequisites, reachability

KINDS = ("npc", "item", "location", "quest")

_TASKS = {
    "npc": (
        "ЗАДАЧА: добавь {n} новых персонажей (NPC) в существующий мир.\n"
        'Верни ТОЛЬКО JSON: {{"entities": {{"<id>": {{"type":"actor","tags":["npc"],'
        '"attrs":{{"hp":10,"hp_max":10}},"desc":"..."}}}}, '
        '"relations": [["<new>","<existing>","<type>",0]]}}\n'
        "- id латиницей, уникальны, НЕ совпадают с существующими;\n"
        "- каждый новый NPC связан relation с существующей сущностью;\n"
        "- НЕ добавляй actions/triggers/endings.\n"),
    "item": (
        "ЗАДАЧА: добавь {n} предметов.\n"
        'Верни ТОЛЬКО JSON: {{"entities": {{"<id>": {{"type":"item","tags":["item"],'
        '"attrs":{{}},"desc":"..."}}}}, "holds": [["<holder>","<item>"]]}}\n'
        "- holder — существующая сущность;\n- НЕ добавляй actions/triggers/endings.\n"),
    "location": (
        "ЗАДАЧА: добавь {n} локаций (мест).\n"
        'Верни ТОЛЬКО JSON: {{"entities": {{"<id>": {{"type":"place","tags":["location"],'
        '"attrs":{{}},"desc":"..."}}}}, "relations": [["<new>","<existing>","near",0]]}}\n'
        "- НЕ добавляй actions/triggers/endings.\n"),
    "quest": (
        "ЗАДАЧА: добавь ОДИН квест (цепочку) из actions/triggers/flags, использующий ТОЛЬКО "
        "существующие сущности.\n"
        'Верни ТОЛЬКО JSON: {{"flags": {{"<name>":0}}, '
        '"actions":[{{"id":"","label":"","pre":[],"eff":[]}}], '
        '"triggers":[{{"pre":[],"eff":[],"once":true}}]}}\n'
        '- НЕ создавай ["end",...];\n'
        "- каждое предусловие должно быть выполнимым (флаг где-то выставляется, предмет где-то даётся);\n"
        "- цепочка из >= 2 шагов, с наградой (флаг/предмет/связь).\n"),
}


def _merge(world, patch):
    w = copy.deepcopy(world)
    for eid, e in (patch.get("entities") or {}).items():
        if eid in w.get("entities", {}):
            raise ValueError(f"entity id exists: {eid}")
        w.setdefault("entities", {})[eid] = e
    for h in (patch.get("holds") or []):
        w.setdefault("holds", []).append(list(h))
    for r in (patch.get("relations") or []):
        w.setdefault("relations", []).append(list(r))
    for a in (patch.get("actions") or []):
        if any(x["id"] == a.get("id") for x in w.get("actions", [])):
            raise ValueError(f"action id exists: {a.get('id')}")
        w.setdefault("actions", []).append(a)
    for t in (patch.get("triggers") or []):
        w.setdefault("triggers", []).append(t)
    for k, v in (patch.get("flags") or {}).items():
        w.setdefault("flags", {}).setdefault(k, v)
    return w


def verify(world, require_endings=True):
    errs = validate(world)
    if errs:
        return errs
    d = dangling_prerequisites(world)
    if d["flags_required_but_never_set"]:
        errs.append(f"dangling flags: {d['flags_required_but_never_set']}")
    if d["items_required_but_never_obtainable"]:
        errs.append(f"dangling items: {d['items_required_but_never_obtainable']}")
    if require_endings:
        r = reachability(world)
        if r["not_found"]:
            errs.append(f"endings no longer reachable: {r['not_found']}")
    return errs


def _llm_generator(world, suffix):
    return gen_json(P.build(P.world_bible(world), suffix))[0]


def add_content(world, kind, n=1, rounds=3, generator=None):
    """-> (new_world|None, info: list[str]). При успехе мир можно записывать и играть."""
    assert kind in KINDS, f"unknown kind: {kind}"
    gen = generator or _llm_generator
    existing = ", ".join(sorted(world.get("entities", {})))
    base = _TASKS[kind].format(n=n) + f"Существующие сущности: {existing}\n"
    suffix, errs = base, []
    for _ in range(rounds):
        patch = gen(world, suffix)
        if not isinstance(patch, dict):
            errs = ["generator returned no JSON"]
            continue
        try:
            w2 = _merge(world, patch)
        except Exception as ex:  # noqa: BLE001 — сообщаем LLM и пробуем снова
            errs = [str(ex)]
            suffix = base + f"\nИСПРАВЬ: {ex}"
            continue
        errs = verify(w2)
        if not errs:
            info = [f"kind={kind}",
                    f"entities+={sorted((patch.get('entities') or {}).keys())}",
                    f"actions+={[a['id'] for a in (patch.get('actions') or [])]}"]
            return w2, info
        suffix = base + "\nИСПРАВЬ ошибки и верни JSON целиком:\n" + "\n".join(errs)
    return None, errs
