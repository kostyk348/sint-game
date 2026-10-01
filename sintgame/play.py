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
from . import memory as M
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


def _referenced_ids(world, said, d):
    text = " ".join(said) + " " + " ".join(d)
    return [i for i in world.get("entities", {}) if i in text]


def _mentioned(world, said, d):
    return {i: world["entities"][i]["desc"]
            for i in _referenced_ids(world, said, d) if world["entities"][i].get("desc")}


def gen_prose(world, tone, label, said, d, cache, use_llm, variety=False, monitor=None,
              history=None, facts=None):
    descs = _mentioned(world, said, d)
    hist = " | ".join((history or [])[-4:])
    facts = facts or []
    key = hashlib.sha1(("|".join([tone, label, "|".join(said), "|".join(d), hist,
                                  json.dumps(descs, ensure_ascii=False, sort_keys=True),
                                  "|".join(facts)])).encode()).hexdigest()[:16]
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
    if facts:
        ctx += f"\nУстановленные ранее факты (долгая память): {' | '.join(facts)}"
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


def play(world_path, script, free, use_prose, variety=False, state_in=None, state_out=None,
         context_n=4, load=None, save=None):
    world = load_world(world_path)
    w = World(world)
    history = []
    flog = M.FactLog()
    turn0 = 0
    if load:
        sess = M.load_session(load)
        w.restore(sess["state"])
        flog = M.FactLog.from_list(sess.get("memory"))
        history = list(sess.get("history") or [])
        turn0 = int(sess.get("turn", 0))
        print(f"  [долгая память: {load} — ход {turn0}, фактов {len(flog.facts)}]")
    if state_in:
        w.restore(json.load(open(state_in)))
        print(f"  [state restored from {state_in}]")
    cache = load_cache()
    monitor = P.PrefixMonitor()
    tone = world.get("tone", "neutral")
    print(f"== {world.get('title')} | tone={tone} | seed={world.get('seed')} ==")
    turns = list(script)

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
        ids = _referenced_ids(world, said, d)
        facts = flog.relevant(ids, k=6)
        txt, src = gen_prose(world, tone, label, said, d, cache, use_prose, variety, monitor,
                             history=(history[-context_n:] if context_n else []), facts=facts)
        if txt:
            print(f"  · {txt}  {src}")
        history.append(label)
        if said or d:
            flog.add(len(history), " ".join(said) if said else label, ids)

    print("\n== END:", w.ended or "-", "|", w.status())
    print("  " + monitor.report())
    if state_out:
        json.dump(w.state(), open(state_out, "w"), ensure_ascii=False)
        print(f"  [state saved to {state_out}]")
    if save:
        M.save_session(save, w.state(), flog.to_list(), history,
                       turn0 + len(history), world.get("title", ""))
        print(f"  [долгая память сохранена: {save} — ход {turn0 + len(history)}, "
              f"фактов {len(flog.facts)}]")


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
