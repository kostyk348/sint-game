"""cli.py — единая точка входа.

  python -m sintgame compile <lore.md> -o world.json
  python -m sintgame validate <world.json>
  python -m sintgame play <world.json> [--script a,b,c] [--free "текст"] [--variety]
"""
import argparse
import json

from . import __version__
from .compile_world import compile_world
from .play import play
from .schema import simulate, validate


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sintgame", description="детерминированный движок LLM-игр")
    ap.add_argument("--version", action="version", version=f"sintgame {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compile", help="lore.md -> world.json (LLM компилирует, валидатор решает)")
    p.add_argument("lore")
    p.add_argument("-o", "--out", default="world.json")
    p.add_argument("--rounds", type=int, default=3)

    p = sub.add_parser("validate", help="схема + инварианты + симуляция достижимости")
    p.add_argument("world")

    p = sub.add_parser("play", help="запустить мир детерминированно")
    p.add_argument("world")
    p.add_argument("--script", default="", help="список action id через запятую")
    p.add_argument("--free", default="", help="свободный ввод игрока (агент-интент + ворота)")
    p.add_argument("--prose", choices=["llm", "none"], default="llm")
    p.add_argument("--variety", action="store_true", help="live-режим: без кэша прозы")
    p.add_argument("--state-in", default=None, help="восстановить состояние (вкл. rng)")
    p.add_argument("--state-out", default=None, help="сохранить состояние (вкл. rng)")

    a = ap.parse_args(argv)

    if a.cmd == "compile":
        world, sim = compile_world(open(a.lore).read(), a.rounds)
        if not world:
            print("COMPILE FAILED")
            return 1
        json.dump(world, open(a.out, "w"), ensure_ascii=False, indent=2)
        print(f"COMPILED -> {a.out}: {world.get('title')}")
        print("SIMULATION:", json.dumps(sim, ensure_ascii=False))
        return 0

    if a.cmd == "validate":
        d = json.load(open(a.world))
        errs = validate(d)
        print("VALIDATOR:", "OK" if not errs else f"{len(errs)} error(s)")
        for e in errs:
            print("  -", e)
        if not errs:
            print("SIMULATION:", json.dumps(simulate(d), ensure_ascii=False))
        return 0 if not errs else 1

    if a.cmd == "play":
        play(a.world, [s.strip() for s in a.script.split(",") if s.strip()],
             a.free, a.prose == "llm", a.variety, a.state_in, a.state_out)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
