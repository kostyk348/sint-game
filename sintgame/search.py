#!/usr/bin/env python3
"""search.py — точный анализ достижимости (BFS) + статический анализ предусловий.

Зачем: симуляция Монте-Карло находит «трудные» концовки 1-2 раза из 300 и ничего
не доказывает. BFS даёт:
  - СВИДЕТЕЛЯ: конкретную последовательность действий, приводящую к концовке;
  - ДОКАЗАТЕЛЬСТВО достижимости, если пространство состояний исчерпано (exhausted);
  - список НЕдостижимых объявленных концовок;
  - тупиковые состояния (нет доступных действий и это не концовка).

Броски кубиков абстрагируются НОМИНАЛОМ (n*(d+1)/2), чтобы пространство было конечно
и не зависело от RNG. Для миров без кубиков анализ точен.

Ограничение: если состояний больше cap — результат INCONCLUSIVE (не доказательство),
и его надо явно так и помечать.
"""
import copy
from collections import deque

from .kernel import World


def _key(st):
    return (
        tuple(sorted(k for k, v in st["flags"].items() if v)),
        tuple(sorted(tuple(h) for h in st["holds"])),
        tuple(sorted((k, v) for k, v in st["rel"].items() if v)),
        tuple(sorted((e, a, v) for e, attrs in st["attrs"].items() for a, v in attrs.items())),
        tuple(st["done"]),
        st["ended"],
    )


def declared_endings(data):
    ends = set()
    for a in data.get("actions", []) or []:
        for x in a.get("eff", []) or []:
            if x and x[0] == "end":
                ends.add(x[1])
    for t in data.get("triggers", []) or []:
        for x in t.get("eff", []) or []:
            if x and x[0] == "end":
                ends.add(x[1])
    return ends


def reachability(data, cap=50000, depth=60, stop_when_all_found=True):
    """BFS по пространству состояний (броски = номинал).

    Свидетель найден -> достижимость ДОКАЗАНА (конструктивно), независимо от cap.
    'Недостижима' можно утверждать ТОЛЬКО при exhausted=True (пространство исчерпано).
    """
    decl = declared_endings(data)
    start = World(copy.deepcopy(data), nominal=True)
    start_st = start.state()
    witnesses, dead_ends = {}, []
    seen = {_key(start_st)}
    q = deque()
    q.append((start_st, ()))
    capped = False
    goal_cap = 100000
    while q:
        if len(seen) > cap or len(seen) > goal_cap:
            capped = True
            break
        if stop_when_all_found and len(witnesses) >= len(decl):
            break
        st, path = q.popleft()
        w = World(copy.deepcopy(data), nominal=True)
        w.restore(st)
        if w.ended:
            witnesses.setdefault(w.ended, path)
            continue
        if len(path) >= depth:
            continue
        acts = w.available()
        if not acts:
            if len(dead_ends) < 8:
                dead_ends.append(path)
            continue
        for a in acts:
            nw = World(copy.deepcopy(data), nominal=True)
            nw.restore(st)
            nw.act(a["id"])
            k = _key(nw.state())
            if k in seen:
                continue
            seen.add(k)
            q.append((nw.state(), path + (a["id"],)))
    not_found = sorted(decl - set(witnesses))
    exhausted = (not q) and not capped
    return {
        "declared": sorted(decl),
        "reachable": {k: list(v) for k, v in witnesses.items()},
        "not_found": not_found,
        "unreachable": not_found if exhausted else [],
        "dead_ends": [list(p) for p in dead_ends],
        "states_explored": len(seen),
        "exhausted": exhausted,
    }


def _produced_and_required(data):
    produced_flags, produced_items = set(), set()
    required_flags, required_items = set(), set()

    def scan_eff(x):
        if not x:
            return
        op = x[0]
        if op == "flag" and x[2] in (1, True):
            produced_flags.add(x[1])
        elif op == "set" and "." not in x[1]:
            produced_flags.add(x[1])
        elif op == "give":
            produced_items.add(x[2])

    def scan_pre(c):
        if not c:
            return
        op = c[0]
        if op == "flag":
            required_flags.add(c[1])
        elif op == "not":
            scan_pre(c[1])  # отрицание: всё равно смотрим вложенное
        elif op == "has":
            required_items.add(c[2])

    for a in data.get("actions", []) or []:
        for x in a.get("eff", []) or []:
            scan_eff(x)
        for c in a.get("pre", []) or []:
            scan_pre(c)
    for t in data.get("triggers", []) or []:
        for x in t.get("eff", []) or []:
            scan_eff(x)
        for c in t.get("pre", []) or []:
            scan_pre(c)

    produced_flags |= {k for k, v in (data.get("flags") or {}).items() if v}
    produced_items |= {i for _, i in (data.get("holds") or [])}
    return (produced_flags, produced_items, required_flags, required_items)


def dangling_prerequisites(data):
    """Флаги/предметы, которые ТРЕБУЮТСЯ, но нигде не производятся -> мертвые предпосылки."""
    pf, pi, rf, ri = _produced_and_required(data)
    return {
        "flags_required_but_never_set": sorted(rf - pf),
        "items_required_but_never_obtainable": sorted(ri - pi),
    }


def diagnose(data, cap=50000):
    """Почему пространство НЕ исчерпывается: какие числовые атрибуты его раздувают.

    Доказательство НЕдостижимости требует исчерпания пространства, а числовые атрибуты
    делают его астрономическим. Показывает реальный диапазон и число различных значений
    по каждому атрибуту — цель для будущей абстракции по порогам.
    """
    start = World(copy.deepcopy(data), nominal=True)
    seen = {_key(start.state())}
    q = deque()
    q.append(start.state())
    vals, capped = {}, False
    while q:
        if len(seen) > cap:
            capped = True
            break
        st = q.popleft()
        w = World(copy.deepcopy(data), nominal=True)
        w.restore(st)
        for ent, attrs in st["attrs"].items():
            for a, v in attrs.items():
                vals.setdefault(f"{ent}.{a}", set()).add(v)
        if w.ended or not w.available():
            continue
        for a in w.available():
            nw = World(copy.deepcopy(data), nominal=True)
            nw.restore(st)
            nw.act(a["id"])
            k = _key(nw.state())
            if k in seen:
                continue
            seen.add(k)
            q.append(nw.state())
    stats = {k: {"distinct": len(s), "min": min(s), "max": max(s)} for k, s in vals.items()}
    dominant = sorted(stats.items(), key=lambda kv: -kv[1]["distinct"])[:8]
    return {"states": len(seen), "capped": capped, "attrs": stats, "dominant": dominant}


def report(data, cap=50000, full=False):
    r = reachability(data, cap=cap, stop_when_all_found=not full)
    d = dangling_prerequisites(data)
    lines = []
    total, got = len(r["declared"]), len(r["reachable"])
    if total and got >= total:
        head = f"reachability: ALL {total} declared endings REACHABLE (witness = proof)"
    elif r["exhausted"]:
        head = f"reachability: EXHAUSTED — proven reachable {got}/{total}"
    else:
        head = f"reachability: PARTIAL {got}/{total} (search capped, not a proof of unreachability)"
    lines.append(head + f", states={r['states_explored']}")
    for e, path in r["reachable"].items():
        lines.append(f"  reachable   {e:>16}  witness({len(path)}): {' -> '.join(path)}")
    for e in r["unreachable"]:
        lines.append(f"  UNREACHABLE {e:>16}  (proven: state space exhausted)")
    for e in r["not_found"]:
        if e not in r["unreachable"]:
            lines.append(f"  not found   {e:>16}  (search capped, unproven)")
    if r["dead_ends"]:
        lines.append(f"  dead-ends encountered: {len(r['dead_ends'])}, e.g. {r['dead_ends'][0]}")
    if d["flags_required_but_never_set"]:
        lines.append(f"  dangling flags (required, never set): {d['flags_required_but_never_set']}")
    if d["items_required_but_never_obtainable"]:
        lines.append(f"  dangling items (required, never obtainable): {d['items_required_but_never_obtainable']}")
    return "\n".join(lines), r, d


if __name__ == "__main__":
    import json
    import sys

    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
    text, _, _ = report(json.load(open(sys.argv[1])))
    print(text)
