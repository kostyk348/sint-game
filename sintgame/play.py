#!/usr/bin/env python3
"""play.py — deterministic runtime loop + GATED free-text understanding + agent prose.

  python3 play.py world.json --script look,talk
  python3 play.py world.json --free "обнять Ию, она плачет"
  python3 play.py world.json

Free text goes through intent.pipeline: resolve against known actions, else the agent
PROPOSES a new action which must pass the GATE before it can touch state. Admitted
actions are persisted (world.json.ext.json) and cached per input (deterministic replay).
Prose is agent-generated and cached by state-delta hash.
"""
import argparse
import hashlib
import json
import os

from . import intent as I
from . import prompt as P
from .cache import path as _cache_path
from .gen import gen_text
from .kernel import World, diff

CACHE_PATH = _cache_path("prose_cache.json")


def ext_path(world_path):
    return world_path + ".ext.json"


def load_world(world_path):
    world = json.load(open(world_path))
    p = ext_path(world_path)
    if os.path.exists(p):
        have = {a["id"] for a in world.get("actions", [])}
        for a in json.load(open(p)):
            if a["id"] not in have:
                world.setdefault("actions", []).append(a)
        print(f"  [world+{len(json.load(open(p)))} admitted runtime action(s)]")
    return world


def save_extension(world_path, action):
    p = ext_path(world_path)
    ext = json.load(open(p)) if os.path.exists(p) else []
    ext.append(action)
    json.dump(ext, open(p, "w"), ensure_ascii=False, indent=2)


def load_cache():
    try:
        return json.load(open(CACHE_PATH))
    except Exception:
        return {}


def _mentioned(world, said, d):
    text = " ".join(said) + " " + " ".join(d)
    out = {}
    for i, e in world.get("entities", {}).items():
        if i in text and e.get("desc"):
            out[i] = e["desc"]
    return out


def gen_prose(world, tone, label, said, d, cache, use_llm, variety=False, monitor=None, history=None):
    descs = _mentioned(world, said, d)
    hist = " | ".join((history or [])[-4:])
    key = hashlib.sha1(("|".join([tone, label, "|".join(said), "|".join(d), hist,
                                  json.dumps(descs, ensure_ascii=False, sort_keys=True)])).encode()).hexdigest()[:16]
    if not variety and key in cache:
        return cache[key], "(cached)"
    if not use_llm:
        return "", "(template)"
    salt = ""
    if variety:
        import os
        salt = "\n(вариант " + hashlib.sha1(os.urandom(8)).hexdigest()[:6] + ")"
    prefix = P.world_bible(world)
    if monitor:
        monitor.note(prefix)
    ctx = ""
    if hist:
        ctx += f"\nНедавние события (для связности): {hist}"
    if descs:
        ctx += f"\nОписания упомянутых сущностей: {json.dumps(descs, ensure_ascii=False)}"
    suffix = (f"ЗАДАЧА: напиши прозу. Действие: {label}\n"
              f"Факты (не меняй, не добавляй новых): {said}\n"
              f"Дельта состояния: {d}{ctx}\n"
              "1-3 предложения от второго лица, СВЯЗНО с недавними событиями. Только текст." + salt)
    txt = gen_text(P.build(prefix, suffix))
    if not variety:
        cache[key] = txt
        json.dump(cache, open(CACHE_PATH, "w"), ensure_ascii=False, indent=2)
    return txt, ("(agent-live)" if variety else "(agent)")


def play(world_path, script, free, use_prose, variety=False, state_in=None, state_out=None, context_n=4):
    world = load_world(world_path)
    w = World(world)
    if state_in:
        w.restore(json.load(open(state_in)))
        print(f"  [state restored from {state_in}]")
    cache = load_cache()
    monitor = P.PrefixMonitor()
    tone = world.get("tone", "neutral")
    print(f"== {world.get('title')} | tone={tone} | seed={world.get('seed')} ==")
    turns = list(script)
    history = []

    while not w.ended:
        label = aid = None
        if turns:
            aid = turns.pop(0)
        elif free:
            free_text, free = free, None
            aid, note, admitted = I.pipeline(free_text, world, w)
            if admitted:
                save_extension(world_path, admitted)
            print(f"\n> [ввод] {free_text}")
            print(f"  <intent> {note}")
            if not aid:
                continue
        else:
            print("\n" + w.status())
            acts = w.available()
            for i, a in enumerate(acts, 1):
                print(f"  {i}. {a['label']}  [{a['id']}]")
            try:
                n = int(input("> ")) - 1
            except (ValueError, EOFError, IndexError):
                break
            aid = acts[n]["id"]
            print()

        # defense in depth: never execute an action whose precondition is false
        if not w.can(aid):
            print(f"  <skip> действие '{aid}' больше недоступно в этом состоянии")
            continue

        before = w.snapshot()
        label = next((a["label"] for a in world["actions"] if a["id"] == aid), aid)
        said = w.act(aid)
        d = diff(before, w.snapshot())
        print(f"\n> {label}")
        for s in said:
            print("  " + s)
        if d:
            print("  [" + "; ".join(d) + "]")
        txt, src = gen_prose(world, tone, label, said, d, cache, use_prose, variety, monitor,
                             history=(history[-context_n:] if context_n else []))
        if txt:
            print(f"  · {txt}  {src}")
        history.append(label)

    print("\n== END:", w.ended or "-", "|", w.status())
    print("  " + monitor.report())
    if state_out:
        json.dump(w.state(), open(state_out, "w"), ensure_ascii=False)
        print(f"  [state saved to {state_out}]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("world")
    ap.add_argument("--script", default="")
    ap.add_argument("--free", default="")
    ap.add_argument("--prose", choices=["llm", "none"], default="llm")
    ap.add_argument("--variety", action="store_true", help="live mode: bypass prose cache (varied, non-deterministic)")
    ap.add_argument("--state-in", default=None, help="restore game state (incl. rng) from JSON")
    ap.add_argument("--state-out", default=None, help="save game state (incl. rng) to JSON")
    a = ap.parse_args()
    play(a.world, [s.strip() for s in a.script.split(",") if s.strip()],
         a.free, a.prose == "llm", a.variety, a.state_in, a.state_out)
