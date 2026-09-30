#!/usr/bin/env python3
"""SINT-GAME spike2 — deterministic kernel (subproject of architecture variant B).

Fixed core + world.json as DATA. Runtime uses zero LLM.
Effects: set add flag give take dmg heal rel say end
Conds:   flag not gt lt ge le eq has rel_gt rel_lt
"""
import random
import re


class World:
    def __init__(self, data, seed=None, nominal=False):
        self.d = data
        self.rng = random.Random(data.get("seed", 0) if seed is None else seed)
        self.nominal = nominal
        self.e = data["entities"]
        self.flags = dict(data.get("flags", {}))
        self.holds = set(tuple(x) for x in data.get("holds", []))
        self.rel = {}
        for a, b, t, w in data.get("relations", []):
            self.rel[(a, b, t)] = w
        self.done = set()
        self.ended = None
        self.said = []
        self.hit_guard = False
        self.last_error = None

    def get(self, path):
        if "." in path:
            ent, att = path.split(".", 1)
            return self.e.get(ent, {}).get("attrs", {}).get(att, 0)
        return self.flags.get(path, 0)

    def set(self, path, val):
        if "." in path:
            ent, att = path.split(".", 1)
            self.e.setdefault(ent, {}).setdefault("attrs", {})[att] = val
        else:
            self.flags[path] = val

    def cond(self, c):
        op = c[0]
        if op == "flag":
            return bool(self.flags.get(c[1], 0))
        if op == "not":
            return not self.cond(c[1])
        if op == "gt":
            return self.get(c[1]) > c[2]
        if op == "lt":
            return self.get(c[1]) < c[2]
        if op == "ge":
            return self.get(c[1]) >= c[2]
        if op == "le":
            return self.get(c[1]) <= c[2]
        if op == "eq":
            return self.get(c[1]) == c[2]
        if op == "has":
            return (c[1], c[2]) in self.holds
        if op == "rel_gt":
            return self.rel.get((c[1], c[2], c[3]), 0) > c[4]
        if op == "rel_lt":
            return self.rel.get((c[1], c[2], c[3]), 0) < c[4]
        return False

    def conds(self, cs):
        return all(self.cond(c) for c in cs)

    def roll(self, expr):
        if isinstance(expr, (int, float)):
            return expr
        if isinstance(expr, dict):
            m = re.match(r"(\d+)d(\d+)", str(expr.get("roll", "0d0")))
            v = 0
            if m:
                n, dz = int(m.group(1)), int(m.group(2))
                if self.nominal:  # абстракция для анализа достижимости: номинал броска
                    v = int(n * (dz + 1) / 2 + 0.5)
                else:
                    v = sum(self.rng.randint(1, dz) for _ in range(n))
            for k in ("plus", "minus"):
                if k in expr:
                    if k == "minus":
                        v -= int(self.get(expr[k]))
                    else:
                        v += int(self.get(expr[k]))
            return v
        return 0

    def eff(self, x):
        op = x[0]
        if op == "set":
            self.set(x[1], x[2])
        elif op == "add":
            self.set(x[1], self.get(x[1]) + x[2])
        elif op == "flag":
            self.flags[x[1]] = x[2]
        elif op == "give":
            self.holds.add((x[1], x[2]))
        elif op == "take":
            self.holds.discard((x[1], x[2]))
        elif op == "dmg":
            self.set(x[1] + ".hp", self.get(x[1] + ".hp") - self.roll(x[2]))
        elif op == "heal":
            self.set(x[1] + ".hp", self.get(x[1] + ".hp") + self.roll(x[2]))
        elif op == "rel":
            k = (x[1], x[2], x[3])
            self.rel[k] = self.rel.get(k, 0) + x[4]
        elif op == "say":
            self.said.append(x[1])
        elif op == "end":
            self.ended = x[1]

    def fire(self):
        changed, guard = True, 0
        while changed and not self.ended and guard < 100:
            changed, guard = False, guard + 1
            for i, t in enumerate(self.d.get("triggers", [])):
                if t.get("once") and i in self.done:
                    continue
                if self.conds(t.get("pre", [])):
                    self.done.add(i)
                    for x in t.get("eff", []):
                        self.eff(x)
                    changed = True
        if guard >= 100:
            self.hit_guard = True

    def available(self):
        return [a for a in self.d.get("actions", []) if self.conds(a.get("pre", []))]

    def _find(self, aid):
        return next((a for a in self.d.get("actions", []) if a["id"] == aid), None)

    def can(self, aid):
        a = self._find(aid)
        return bool(a) and self.conds(a.get("pre", []))

    def act(self, aid, strict=False):
        """Execute an action. Refuses if its precondition is false (the fix for
        'cache returns an action that is no longer valid')."""
        self.said = []
        self.last_error = None
        a = self._find(aid)
        if not a:
            self.last_error = "no such action"
            return []
        if not self.conds(a.get("pre", [])):
            self.last_error = "unavailable"
            if strict:
                raise ValueError(f"action '{aid}' unavailable in current state")
            return []
        for x in a.get("eff", []):
            self.eff(x)
        self.fire()
        return self.said

    def state(self):
        """Full serializable state, INCLUDING rng — the fix for save/load desync."""
        st = self.rng.getstate()
        return {
            "flags": dict(self.flags),
            "attrs": {e: dict(v.get("attrs", {})) for e, v in self.e.items()},
            "holds": sorted(tuple(h) for h in self.holds),
            "rel": {f"{a}|{b}|{t}": w for (a, b, t), w in self.rel.items()},
            "done": sorted(self.done),
            "ended": self.ended,
            "rng": {"version": st[0], "internal": list(st[1]), "gauss": st[2]},
        }

    def restore(self, s):
        self.flags = dict(s["flags"])
        for e, attrs in s["attrs"].items():
            self.e.setdefault(e, {}).setdefault("attrs", {}).update(attrs)
        self.holds = set(tuple(h) for h in s["holds"])
        self.rel = {}
        for k, w in s["rel"].items():
            a, b, t = k.split("|")
            self.rel[(a, b, t)] = w
        self.done = set(s["done"])
        self.ended = s["ended"]
        r = s["rng"]
        self.rng.setstate((r["version"], tuple(r["internal"]), r["gauss"]))

    def snapshot(self):
        return {
            "flags": dict(self.flags),
            "attrs": {e: dict(v.get("attrs", {})) for e, v in self.e.items()},
            "holds": sorted(tuple(h) for h in self.holds),
            "rel": {f"{a}>{b}:{t}": w for (a, b, t), w in self.rel.items()},
        }

    def status(self):
        p = self.e.get("player", {}).get("attrs", {})
        parts = [f"{k}={v}" for k, v in p.items()]
        fl = ",".join(k for k, v in self.flags.items() if v)
        return " ".join(parts) + (f" | flags=[{fl}]" if fl else "")


def diff(before, after):
    out = []
    for k in after["attrs"]:
        b = before["attrs"].get(k, {})
        for a2, v in after["attrs"][k].items():
            if b.get(a2) != v:
                out.append(f"{k}.{a2}: {b.get(a2)} -> {v}")
    for k, v in after["flags"].items():
        if before["flags"].get(k) != v:
            out.append(f"flag {k}: {before['flags'].get(k)} -> {v}")
    ah, bh = set(map(tuple, after["holds"])), set(map(tuple, before["holds"]))
    for h, it in ah - bh:
        out.append(f"+ {it} -> {h}")
    for h, it in bh - ah:
        out.append(f"- {it} from {h}")
    for k, v in after["rel"].items():
        if before["rel"].get(k) != v:
            out.append(f"rel {k}: {before['rel'].get(k)} -> {v}")
    return out
