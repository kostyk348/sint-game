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
from .search import report as reach_report


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sintgame", description="детерминированный движок LLM-игр")
    ap.add_argument("--version", action="version", version=f"sintgame {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compile", help="lore.md -> world.json (LLM компилирует, валидатор решает)")
    p.add_argument("lore")
    p.add_argument("-o", "--out", default="world.json")
    p.add_argument("--rounds", type=int, default=3)

    p = sub.add_parser("validate", help="схема + инварианты + достижимость (BFS со свидетелями)")
    p.add_argument("world")
    p.add_argument("--full", action="store_true", help="полный обход (искать тупики/недостижимость, медленнее)")

    p = sub.add_parser("balance", help="распределение концовок по многим прогонам (баланс)")
    p.add_argument("world")
    p.add_argument("--trials", type=int, default=2000)

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
            print(reach_report(d, full=a.full)[0])
        return 0 if not errs else 1

    if a.cmd == "balance":
        d = json.load(open(a.world))
        sim = simulate(d, trials=a.trials)
        dist = sim["endings_reached"]
        total = sum(dist.values()) or 1
        print(f"balance: {a.trials} trials | no_ending={sim['no_ending']} "
              f"dead_ends={sim['dead_ends']} unstable={sim['unstable']}")
        for k, v in sorted(dist.items(), key=lambda x: -x[1]):
            print(f"  {k:>16}  {v:5}  {v / total:6.1%}")
        if dist and max(dist.values()) / total > 0.7:
            print("  WARNING: доминирующая концовка (>70%) — вероятный дисбаланс")
        return 0

    if a.cmd == "play":
        play(a.world, [s.strip() for s in a.script.split(",") if s.strip()],
             a.free, a.prose == "llm", a.variety, a.state_in, a.state_out)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
