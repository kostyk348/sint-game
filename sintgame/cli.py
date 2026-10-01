"""cli.py — единая точка входа.

  python -m sintgame compile <lore.md> -o world.json
  python -m sintgame validate <world.json>
  python -m sintgame play <world.json> [--script a,b,c] [--free "текст"] [--variety]
"""
import argparse
import json

from . import __version__
from . import memory as mem
from .compact import compact
from .compile_world import compile_world
from .content import KINDS, add_content
from .editor import write_editor
from .play import play
from .run import report as soak_report
from .sandbox import director_llm, report as sandbox_report
from .serve import run as serve_run
from .schema import simulate, validate
from .search import diagnose, report as reach_report
from .tune import tune


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sintgame", description="детерминированный движок LLM-игр")
    ap.add_argument("--version", action="version", version=f"sintgame {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compile", help="lore.md -> world.json (LLM компилирует, валидатор решает)")
    p.add_argument("lore")
    p.add_argument("-o", "--out", default="world.json")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--sandbox", action="store_true", help="открытый мир без обязательных концовок")

    p = sub.add_parser("validate", help="схема + инварианты + достижимость (BFS со свидетелями)")
    p.add_argument("world")
    p.add_argument("--full", action="store_true", help="полный обход (искать тупики/недостижимость, медленнее)")

    p = sub.add_parser("balance", help="распределение концовок по многим прогонам (баланс)")
    p.add_argument("world")
    p.add_argument("--trials", type=int, default=2000)

    p = sub.add_parser("add", help="сгенерировать контент в мир (npc/item/location/quest) под верификацией")
    p.add_argument("world")
    p.add_argument("--kind", choices=list(KINDS), required=True)
    p.add_argument("-n", type=int, default=1)
    p.add_argument("-o", "--out", default="")

    p = sub.add_parser("compact", help="свернуть admitted-действия (.ext.json) в мир и перевалидировать")
    p.add_argument("world")
    p.add_argument("-o", "--out", default="")

    p = sub.add_parser("diagnose", help="почему достижимость не исчерпывается (какие атрибуты раздувают)")
    p.add_argument("world")
    p.add_argument("--cap", type=int, default=50000)

    p = sub.add_parser("editor", help="самодостаточный HTML-редактор мира (граф + свидетели + JSON)")
    p.add_argument("world")
    p.add_argument("-o", "--out", default="")

    p = sub.add_parser("run", help="полноценный прогон N ходов с проверкой инвариантов")
    p.add_argument("world")
    p.add_argument("--turns", type=int, default=60)
    p.add_argument("--policy", choices=["random", "explore", "greedy", "linger"], default="explore")
    p.add_argument("--seed", type=int, default=0)

    p = sub.add_parser("tune", help="авто-тюнинг чисел мира под баланс концовок")
    p.add_argument("world")
    p.add_argument("-o", "--out", default="")
    p.add_argument("--trials", type=int, default=300)
    p.add_argument("--iters", type=int, default=80)
    p.add_argument("--seed", type=int, default=0)

    p = sub.add_parser("sandbox", help="открытый песочный режим: долгие прогоны (500+ шагов) + директор")
    p.add_argument("world")
    p.add_argument("--turns", type=int, default=500)
    p.add_argument("--policy", choices=["random", "explore", "greedy", "linger"], default="linger")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--every", type=int, default=0, help="каждые N ходов звать директора (0 = выкл)")
    p.add_argument("--director", choices=["none", "llm"], default="none")

    p = sub.add_parser("serve", help="локальный веб-чат с персонажами (аналог character.ai, на ноуте)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--characters", default="", help="каталог JSON-карточек персонажей")
    p.add_argument("--world", action="append", default=[], help="world.json (NPC → персонажи); можно несколько")

    p = sub.add_parser("memory", help="показать долгую память сохранённой сессии")
    p.add_argument("save")

    p = sub.add_parser("play", help="запустить мир детерминированно")
    p.add_argument("world")
    p.add_argument("--script", default="", help="список action id через запятую")
    p.add_argument("--free", default="", help="свободный ввод игрока (агент-интент + ворота)")
    p.add_argument("--prose", choices=["llm", "none"], default="llm")
    p.add_argument("--variety", action="store_true", help="live-режим: без кэша прозы")
    p.add_argument("--context", type=int, default=4, help="сколько недавних событий давать в прозу (0 = выкл)")
    p.add_argument("--state-in", default=None, help="восстановить состояние (вкл. rng)")
    p.add_argument("--state-out", default=None, help="сохранить состояние (вкл. rng)")
    p.add_argument("--load", default=None, help="загрузить ДОЛГУЮ ПАМЯТЬ + состояние (session.json)")
    p.add_argument("--save", default=None, help="сохранить ДОЛГУЮ ПАМЯТЬ + состояние")

    a = ap.parse_args(argv)

    if a.cmd == "compile":
        world, sim = compile_world(open(a.lore).read(), a.rounds, sandbox=a.sandbox)
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
              f"dead_ends={sim['dead_ends']} unstable={sim['unstable']} avg_turns={sim['avg_turns']}")
        for k, v in sorted(dist.items(), key=lambda x: -x[1]):
            print(f"  {k:>16}  {v:5}  {v / total:6.1%}")
        if dist and max(dist.values()) / total > 0.7:
            print("  WARNING: доминирующая концовка (>70%) — вероятный дисбаланс; попробуйте `sintgame tune`")
        return 0

    if a.cmd == "editor":
        print(f"EDITOR -> {write_editor(a.world, a.out or None)}")
        return 0

    if a.cmd == "run":
        d = json.load(open(a.world))
        text, r = soak_report(d, turns=a.turns, policy=a.policy, seed=a.seed)
        print(text)
        return 0 if not r["violations"] else 2

    if a.cmd == "tune":
        d = json.load(open(a.world))
        tuned, info = tune(d, trials=a.trials, iters=a.iters, seed=a.seed)
        out = a.out or a.world
        json.dump(tuned, open(out, "w"), ensure_ascii=False, indent=2)
        print(f"TUNED -> {out}: " + json.dumps(info, ensure_ascii=False))
        return 0

    if a.cmd == "add":
        d = json.load(open(a.world))
        w2, info = add_content(d, a.kind, a.n)
        if not w2:
            print("ADD FAILED:")
            for x in info:
                print("  -", x)
            return 1
        out = a.out or a.world
        json.dump(w2, open(out, "w"), ensure_ascii=False, indent=2)
        print(f"ADDED -> {out}: " + "; ".join(info))
        return 0

    if a.cmd == "compact":
        w2, info = compact(a.world, a.out or None)
        if not w2:
            print("COMPACT FAILED:")
            for x in info:
                print("  -", x)
            return 1
        print(f"COMPACTED -> {a.out or a.world}: " + "; ".join(info))
        return 0

    if a.cmd == "diagnose":
        d = json.load(open(a.world))
        r = diagnose(d, cap=a.cap)
        print(f"diagnose: states={r['states']} capped={r['capped']}")
        for k, v in r["dominant"]:
            print(f"  {k:>22}  distinct={v['distinct']:>5}  range=[{v['min']}, {v['max']}]")
        if r["capped"]:
            print("  -> недостижимость НЕ доказывается: пространство не исчерпано; "
                  "атрибуты выше — кандидаты на абстракцию по порогам")
        return 0

    if a.cmd == "sandbox":
        d = json.load(open(a.world))
        director = director_llm if (a.director == "llm" and a.every) else None
        text, r = sandbox_report(d, turns=a.turns, policy=a.policy, seed=a.seed,
                                 director=director, every=a.every)
        print(text)
        return 0 if not r["violations"] else 2

    if a.cmd == "memory":
        s = mem.load_session(a.save)
        print(f"world: {s.get('world', '')} | ход: {s.get('turn', 0)} | "
              f"фактов: {len(s.get('memory') or [])}")
        for f in (s.get("memory") or [])[-12:]:
            print("  -", f.get("text") if isinstance(f, dict) else str(f))
        st = s.get("state") or {}
        if st.get("ended"):
            print("  концовка:", st["ended"])
        return 0

    if a.cmd == "serve":
        serve_run(host=a.host, port=a.port, worlds=a.world or None,
                  character_dir=a.characters or None)
        return 0

    if a.cmd == "play":
        play(a.world, [s.strip() for s in a.script.split(",") if s.strip()],
             a.free, a.prose == "llm", a.variety, a.state_in, a.state_out, a.context,
             a.load, a.save)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
