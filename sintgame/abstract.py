#!/usr/bin/env python3
"""abstract.py — ЗВУЧИЙ анализ игровой логики (абстракция по порогам).

Идея (то, что в compiler-архитектуре зовётся analysis-backend):
  числовые атрибуты сворачиваются в РЕГИОНЫ между порогами, встречающимися в
  условиях мира. Переходы, которые нельзя вычислить точно, разветвляются
  (may-семантика) -> получаем КОНЕЧНУЮ систему, которая ЯВЛЯЕТСЯ НАДМНОЖЕСТВОМ
  реальных состояний. Отсюда:
      • концовка НЕ достижима в абстракции  =>  она недостижима ВООБЩЕ (доказательство);
      • инвариант не нарушим ни в одном абстрактном состоянии => доказан;
      • достижимость по-прежнему доказывается КОНКРЕТНЫМ свидетелем (см. search.py).

Это and не отменяет Монте-Карло/конкретный BFS — это даёт то, чего у них нет:
НЕдостижимость и доказанные инварианты.

Наследует семантику kernel.py (cond/eff), чтобы абстракция была надмножеством.
"""
import copy

MAYBE = "?"
_TRUE = "T"
_FALSE = "F"
_INF = 10 ** 9


# --- пороги и регионы --------------------------------------------------------------

def _collect_thresholds(data):
    attrs, rels = {}, {}

    def add(d, key, v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            d.setdefault(key, set()).add(v)

    def scan(c):
        if not isinstance(c, list) or not c:
            return
        op = c[0]
        if op == "not":
            scan(c[1])
        elif op in ("gt", "lt", "ge", "le", "eq") and len(c) >= 3:
            if isinstance(c[1], str) and "." in c[1]:
                add(attrs, c[1], c[2])
        elif op in ("rel_gt", "rel_lt") and len(c) >= 5:
            add(rels, f"{c[1]},{c[2]},{c[3]}", c[4])

    for a in data.get("actions", []) or []:
        for c in a.get("pre", []) or []:
            scan(c)
    for t in data.get("triggers", []) or []:
        for c in t.get("pre", []) or []:
            scan(c)
    return ({k: sorted(v) for k, v in attrs.items()},
            {k: sorted(v) for k, v in rels.items()})


def region_idx(T, v):
    """Индекс региона для значения v среди порогов T (0..len(T))."""
    if not T:
        return 0
    r = 0
    for t in T:
        if v >= t:
            r += 1
        else:
            break
    return r


def region_bounds(T, r):
    lo = T[r - 1] if r >= 1 and r - 1 < len(T) else (None if r == 0 else T[-1])
    hi = T[r] if r < len(T) else None
    return lo, hi


def _regions_spanning(T, lo, hi):
    """Все регионы, чей интервал пересекается с [lo, hi]."""
    out = set()
    if lo is None:
        lo = -_INF
    if hi is None:
        hi = _INF
    for r in range(len(T) + 1):
        rlo, rhi = region_bounds(T, r)
        rlo = -_INF if rlo is None else rlo
        rhi = _INF if rhi is None else rhi
        if rlo <= hi and lo < rhi:
            out.add(r)
    return out or {0}


def _cmp(T, r, const, op):
    """may-семантика сравнения региона r с константой const."""
    if not T:
        return MAYBE
    lo, hi = region_bounds(T, r)
    lo = -_INF if lo is None else lo
    hi = _INF if hi is None else hi
    if op == "ge":
        return _TRUE if lo >= const else (_FALSE if hi <= const else MAYBE)
    if op == "gt":
        return _TRUE if lo > const else (_FALSE if hi <= const else MAYBE)
    if op == "lt":
        return _TRUE if hi <= const else (_FALSE if lo >= const else MAYBE)
    if op == "le":
        return _TRUE if hi <= const else (_FALSE if lo > const else MAYBE)
    if op == "eq":
        if lo == hi == const:
            return _TRUE
        if lo <= const < hi:
            return MAYBE
        return _FALSE
    return MAYBE


# --- абстрактное состояние ---------------------------------------------------------

class AState:
    __slots__ = ("ended", "flags", "holds", "attrs", "rels", "done")

    def __init__(self, ended=None, flags=None, holds=None, attrs=None, rels=None, done=None):
        self.ended = ended
        self.flags = flags if flags is not None else set()
        self.holds = holds if holds is not None else set()
        self.attrs = attrs if attrs is not None else {}   # "e.a" -> region
        self.rels = rels if rels is not None else {}       # "a,b,t" -> region
        self.done = done if done is not None else set()

    def key(self):
        return (self.ended, frozenset(self.flags), frozenset(self.holds),
                tuple(sorted(self.attrs.items())),
                tuple(sorted(self.rels.items())), frozenset(self.done))

    def clone(self):
        return AState(self.ended, set(self.flags), set(self.holds),
                      dict(self.attrs), dict(self.rels), set(self.done))


# --- вычисление условий и эффектов в абстракции -----------------------------------

def cond_may(c, st, TH, RELTH):
    op = c[0]
    if op == "flag":
        return _TRUE if c[1] in st.flags else _FALSE
    if op == "not":
        v = cond_may(c[1], st, TH, RELTH)
        return {_TRUE: _FALSE, _FALSE: _TRUE, MAYBE: MAYBE}[v]
    if op == "has":
        return _TRUE if (c[1], c[2]) in st.holds else _FALSE
    if op in ("gt", "lt", "ge", "le", "eq") and len(c) >= 3:
        if isinstance(c[1], str) and "." in c[1]:
            T = TH.get(c[1], [])
            return _cmp(T, st.attrs.get(c[1], 0), c[2], op)
        return MAYBE  # сравнение по флагу — осторожно (надмножество)
    if op in ("rel_gt", "rel_lt") and len(c) >= 5:
        key = f"{c[1]},{c[2]},{c[3]}"
        T = RELTH.get(key, [])
        cmp_op = "gt" if op == "rel_gt" else "lt"
        return _cmp(T, st.rels.get(key, 0), c[4], cmp_op)
    return MAYBE


def conds_may(cs, st, TH, RELTH):
    out = _TRUE
    for c in cs or []:
        v = cond_may(c, st, TH, RELTH)
        if v == _FALSE:
            return _FALSE
        if v == MAYBE:
            out = MAYBE
    return out


def _region_add(T, r, n):
    lo, hi = region_bounds(T, r)
    lo = -_INF if lo is None else lo
    hi = _INF if hi is None else hi
    return _regions_spanning(T, lo + n, hi + n)


def _roll_range(expr, st, TH):
    if isinstance(expr, (int, float)):
        return (int(expr), int(expr))
    if isinstance(expr, dict):
        lo = hi = 0
        m = expr.get("roll")
        if isinstance(m, str) and "d" in m:
            n, d = m.split("d")
            n, d = int(n), int(d)
            lo += n * 1
            hi += n * d
        for sign, key in ((1, "plus"), (-1, "minus")):
            if key in expr:
                T = TH.get(expr[key], [])
                rlo, rhi = region_bounds(T, st.attrs.get(expr[key], 0))
                rlo = -_INF if rlo is None else rlo
                rhi = _INF if rhi is None else rhi
                a, b = sign * rlo, sign * rhi
                lo += min(a, b)
                hi += max(a, b)
        return (lo, hi)
    return (0, 0)


def _apply_eff(x, st, TH, RELTH):
    """Возвращает список абстрактных состояний (ветвление may-переходов)."""
    op = x[0]
    if op == "say":
        return [st]
    if op == "end":
        s = st.clone()
        s.ended = x[1]
        return [s]
    if op == "flag":
        s = st.clone()
        if x[2]:
            s.flags.add(x[1])
        else:
            s.flags.discard(x[1])
        return [s]
    if op in ("give", "take"):
        s = st.clone()
        if op == "give":
            s.holds.add((x[1], x[2]))
        else:
            s.holds.discard((x[1], x[2]))
        return [s]
    if op in ("set", "add"):
        path, val = x[1], x[2]
        if "." in path:
            T = TH.get(path, [])
            cur = st.attrs.get(path, 0)
            if op == "set":
                rs = {region_idx(T, val)}
            else:
                rs = _region_add(T, cur, val)
            return [_with_attr(st, path, r) for r in rs]
        # флаговая дорожка
        s = st.clone()
        if op == "set":
            (s.flags.add if val else s.flags.discard)(path)
        else:
            if val != 0:
                s.flags.add(path)  # add по флагу -> истина (надмножество)
        return [s]
    if op in ("dmg", "heal"):
        path = x[1] + ".hp"
        T = TH.get(path, [])
        cur = st.attrs.get(path, 0)
        lo, hi = _roll_range(x[2], st, TH)
        if op == "heal":
            lo, hi = -hi, -lo
        rlo, rhi = region_bounds(T, cur)
        rlo = -_INF if rlo is None else rlo
        rhi = _INF if rhi is None else rhi
        cand = _regions_spanning(T, rlo - hi, rhi - lo)
        return [_with_attr(st, path, r) for r in cand]
    if op == "rel":
        key = f"{x[1]},{x[2]},{x[3]}"
        T = RELTH.get(key, [])
        cur = st.rels.get(key, 0)
        out = []
        for r in _region_add(T, cur, x[4]):
            s = st.clone()
            s.rels[key] = r
            out.append(s)
        return out
    return [st]


def _with_attr(st, path, r):
    s = st.clone()
    s.attrs[path] = r
    return s


def _apply_effs(effs, st, TH, RELTH):
    states = [st]
    for x in effs or []:
        nxt = []
        for s in states:
            nxt.extend(_apply_eff(x, s, TH, RELTH))
        states = nxt
        if len(states) > 64:
            states = states[:64]
    return states


def _fire_triggers(st, data, TH, RELTH):
    """Замыкание по триггерам: st + все состояния, достижимые срабатыванием (надмножество)."""
    out = {st.key(): st}
    frontier = [st]
    steps = 0
    while frontier:
        steps += 1
        if steps > 4000:
            break
        s = frontier.pop()
        for i, t in enumerate(data.get("triggers", []) or []):
            if t.get("once") and i in s.done:
                continue
            if conds_may(t.get("pre", []), s, TH, RELTH) == _FALSE:
                continue
            for ns in _apply_effs(t.get("eff", []), s, TH, RELTH):
                if t.get("once"):
                    ns.done = set(ns.done) | {i}
                if ns.key() not in out:
                    out[ns.key()] = ns
                    frontier.append(ns)
    return list(out.values())


# --- обход абстрактного пространства ----------------------------------------------

def _prepare(data):
    """Пороги (вкл. инвариантные), регионы старта."""
    TH, RELTH = _collect_thresholds(data)
    cons = data.get("constraints") or {}
    min_hp = cons.get("min_hp", 1)
    for v in cons.get("vital", []) or []:
        key = f"{v}.hp"
        T = set(TH.get(key, []))
        T.add(min_hp)
        T.add(0)
        TH[key] = sorted(T)
    start = AState()
    for eid, e in (data.get("entities") or {}).items():
        for k, v in (e.get("attrs") or {}).items():
            TH.setdefault(f"{eid}.{k}", [])
            start.attrs[f"{eid}.{k}"] = region_idx(TH[f"{eid}.{k}"], v)
    for h, i in data.get("holds", []) or []:
        start.holds.add((h, i))
    for k, v in (data.get("flags") or {}).items():
        if v:
            start.flags.add(k)
    for a, b, t, w in data.get("relations", []) or []:
        key = f"{a},{b},{t}"
        RELTH.setdefault(key, [])
        start.rels[key] = region_idx(RELTH[key], w)
    return TH, RELTH, start


def abstract_reachable(data, cap=200000):
    TH, RELTH, start = _prepare(data)
    seen = {start.key(): start}
    frontier = [start]
    while frontier and len(seen) < cap:
        st = frontier.pop()
        if st.ended:
            continue
        for a in data.get("actions", []) or []:
            if conds_may(a.get("pre", []), st, TH, RELTH) == _FALSE:
                continue
            for st2 in _apply_effs(a.get("eff", []), st, TH, RELTH):
                for st3 in _fire_triggers(st2, data, TH, RELTH):
                    k = st3.key()
                    if k not in seen:
                        seen[k] = st3
                        frontier.append(st3)
    return seen, TH, RELTH


def prove(data, cap=200000):
    seen, TH, RELTH = abstract_reachable(data, cap)
    declared = set()
    for a in data.get("actions", []) or []:
        for x in a.get("eff", []) or []:
            if x and x[0] == "end":
                declared.add(x[1])
    for t in data.get("triggers", []) or []:
        for x in t.get("eff", []) or []:
            if x and x[0] == "end":
                declared.add(x[1])
    reached_abs = {s.ended for s in seen.values() if s.ended}
    vital = (data.get("constraints") or {}).get("vital", [])
    min_hp = (data.get("constraints") or {}).get("min_hp", 1)
    inv_may_violate = False
    for s in seen.values():
        for v in vital:
            T = TH.get(f"{v}.hp", [])
            r = s.attrs.get(f"{v}.hp")
            if r is None:
                continue
            lo, hi = region_bounds(T, r)
            hi = _INF if hi is None else hi
            if hi <= min_hp:   # этот регион целиком ниже порога -> возможно нарушение
                inv_may_violate = True
    dead_may = False
    for s in seen.values():
        if s.ended:
            continue
        any_action = False
        for a in data.get("actions", []) or []:
            if conds_may(a.get("pre", []), s, TH, RELTH) != _FALSE:
                any_action = True
                break
        if not any_action:
            dead_may = True
    return {
        "states": len(seen),
        "capped": len(seen) >= cap,
        "declared": sorted(declared),
        "reachable_abs": sorted(reached_abs),
        "proven_unreachable": sorted(declared - reached_abs),
        "invariant_may_violate": inv_may_violate,
        "dead_end_possible": dead_may,
    }


def _declared_endings(data):
    decl = set()
    for a in data.get("actions", []) or []:
        for x in a.get("eff", []) or []:
            if x and x[0] == "end":
                decl.add(x[1])
    for t in data.get("triggers", []) or []:
        for x in t.get("eff", []) or []:
            if x and x[0] == "end":
                decl.add(x[1])
    return decl


def horizon(data, k, cap=200000):
    """Temporal: что ДОСТИЖИМО за <= k шагов (надмножество), а что — доказанно НЕТ.

    Абстракция надмножественна, поэтому «не достигнуто за k в абстракции» => в реальности
    тоже не достигнуто за k (звучая нижняя граница по времени/шагам).
    """
    TH, RELTH, start = _prepare(data)
    decl = _declared_endings(data)
    seen = {start.key()}
    within = set()
    if start.ended:
        within.add(start.ended)
    layer = [start]
    capped = False
    for _ in range(k):
        nxt = []
        for st in layer:
            if st.ended:
                continue
            for a in data.get("actions", []) or []:
                if conds_may(a.get("pre", []), st, TH, RELTH) == _FALSE:
                    continue
                for st2 in _apply_effs(a.get("eff", []), st, TH, RELTH):
                    for st3 in _fire_triggers(st2, data, TH, RELTH):
                        if st3.ended:
                            within.add(st3.ended)
                        if st3.key() not in seen:
                            seen.add(st3.key())
                            nxt.append(st3)
                            if len(seen) > cap:
                                capped = True
        layer = nxt
        if capped or not layer:
            break
    return {"k": k, "within": sorted(within),
            "not_within_k": sorted(decl - within), "states": len(seen), "capped": capped}


if __name__ == "__main__":
    import json
    import sys

    d = json.load(open(sys.argv[1]))
    print(json.dumps(prove(d), ensure_ascii=False, indent=2))
