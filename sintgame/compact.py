#!/usr/bin/env python3
"""compact.py — свернуть накопленные рантайм-действия (.ext.json) в мир (v2).

Долгая игра порождает admitted-действия (sidecar `<world>.ext.json`). Компакция склеивает
их в один `world.json`, дедуплицирует по id и ПЕРЕВАЛИДИРУЕТ (схема + мёртвые предпосылки +
достижимость концовок). Это оффлайн-проход; рантайм только читает результат.
"""
import json
import os

from .content import verify


def ext_path(world_path):
    return world_path + ".ext.json"


def load_merged(world_path):
    world = json.load(open(world_path))
    p = ext_path(world_path)
    ext = json.load(open(p)) if os.path.exists(p) else []
    return world, ext


def compact(world_path, out_path=None, require_endings=True, drop_ext=None):
    world, ext = load_merged(world_path)
    have = {a["id"] for a in world.get("actions", [])}
    folded, skipped = [], 0
    for a in ext:
        if a.get("id") in have:
            skipped += 1
            continue
        world.setdefault("actions", []).append(a)
        have.add(a["id"])
        folded.append(a["id"])

    errs = verify(world, require_endings=require_endings)
    if errs:
        return None, errs

    out = out_path or world_path
    json.dump(world, open(out, "w"), ensure_ascii=False, indent=2)
    # если сворачиваем на месте — ext больше не нужен (иначе снова задублируется)
    if (drop_ext is None and out == world_path) or drop_ext:
        p = ext_path(world_path)
        if os.path.exists(p):
            os.remove(p)
    info = [f"folded={folded}", f"duplicates_skipped={skipped}",
            f"actions_total={len(world.get('actions', []))}"]
    return world, info
