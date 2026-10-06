#!/usr/bin/env python3
"""lorebook.py — память как ЛОРБУК (глубина вместо плоского списка фактов).

Классическая модель (SillyTavern / Character.ai):
  • у записи есть КЛЮЧИ; запись активируется, если ключ встречается в контексте;
  • активация РЕКУРСИВНА: активная запись «тянет» другие по ключам в своём тексте;
  • есть ПОСТОЯННЫЕ записи (всегда) и ПРИОРИТЕТ;
  • в промпт идёт ОГРАНИЧЕННЫЙ БЮДЖЕТ из самых релевантных записей.

Наш вклад: выбор набора записей — это НАБОР boolean-решений. Их можно взять
ЛОГИТАМИ модели (`selection_schema` + algebra_json_logits), а не порогом похожести —
это и есть «память через логиты».
"""
import re


def _tokens(s):
    return set(re.findall(r"[0-9a-zA-Zа-яА-ЯёЁ_]+", (s or "").lower()))


class Lorebook:
    def __init__(self, entries=None):
        self.entries = [dict(e) for e in (entries or [])]

    # --- построение из мира (сущности -> записи) ---
    @classmethod
    def from_world(cls, world):
        out = []
        for eid, e in (world.get("entities") or {}).items():
            keys = [eid]
            keys += _tokens(e.get("desc", "")) and list(_tokens(e.get("desc", "")))[:3] or []
            content = (str(e.get("desc", "")) + " " + str(e.get("voice", ""))).strip()
            out.append({"id": f"ent_{eid}", "keys": list(dict.fromkeys(keys)),
                        "content": content or eid, "priority": 0, "constant": False,
                        "recursive": True})
        return cls(out)

    def by_id(self, eid):
        for e in self.entries:
            if e["id"] == eid:
                return e
        return None

    # --- активация (ключи + рекурсия + постоянные) ---
    def scan(self, text, entity_ids=None):
        low = (text or "").lower()
        ids = set(entity_ids or [])
        active = set()
        for e in self.entries:
            if e.get("constant"):
                active.add(e["id"])
                continue
            for k in e.get("keys", []):
                if k.lower() in low or k in ids:
                    active.add(e["id"])
                    break
        changed = True
        while changed:
            changed = False
            for e in list(self.entries):
                if e["id"] not in active or not e.get("recursive"):
                    continue
                body = (e.get("content", "") or "").lower()
                for e2 in self.entries:
                    if e2["id"] in active:
                        continue
                    for k in e2.get("keys", []):
                        if k.lower() in body:
                            active.add(e2["id"])
                            changed = True
                            break
        return active

    def score(self, text, eid):
        e = self.by_id(eid)
        if not e:
            return 0
        low = (text or "").lower()
        s = int(e.get("priority", 0))
        if e.get("constant"):
            s += 3
        for k in e.get("keys", []):
            if k.lower() in low:
                s += 2
        return s

    def select(self, text, budget=1200, entity_ids=None):
        active = self.scan(text, entity_ids)
        ranked = sorted(active, key=lambda i: (-self.score(text, i), i))
        chosen, used = [], 0
        for eid in ranked:
            e = self.by_id(eid)
            if not e:
                continue
            ln = len(e.get("content", ""))
            if used + ln > budget and chosen:
                continue
            chosen.append(eid)
            used += ln
        return chosen

    @classmethod
    def from_facts(cls, facts):
        """Наши долгие факты (FactLog) -> записи лорбука (ключи = сущности факта)."""
        out = []
        for i, f in enumerate(facts or []):
            if isinstance(f, dict):
                ents = list(f.get("entities") or [])
                txt = str(f.get("text", ""))
                turn = int(f.get("turn", i))
            else:
                ents, txt, turn = [], str(f), i
            out.append({"id": f"fact_{turn}_{i}", "keys": ents, "content": txt,
                        "priority": 1, "constant": False, "recursive": True})
        return cls(out)

    @staticmethod
    def finalize(ids, decision, constants=None):
        """Итог: постоянные всегда + выбранные логитами."""
        kept = set(constants or [])
        kept |= set(Lorebook.apply(ids, decision))
        return [i for i in ids if i in kept]

    # --- выбор через ЛОГИТЫ -----------------------------------------------------
    def selection_schema(self, ids):
        """JSON-схема: по булеву решению на каждую запись. Отдать логитам модели."""
        return {
            "type": "object",
            "properties": {i: {"type": "boolean"} for i in ids},
            "required": list(ids),
        }

    @staticmethod
    def apply(ids, decision):
        return [i for i in ids if bool((decision or {}).get(i))]


class LayeredMemory:
    """Слоёная память: constant (ядро) + мир (статика) + сага (долгие факты) + сцена.
    ОДИН бюджет на все слои; постоянные — всегда, остальное — по ключам и приоритету."""

    def __init__(self, budget=1000):
        self.budget = int(budget)
        self.constants = []
        self.layers = {}

    def add_constant(self, text):
        if text:
            self.constants.append(str(text))
        return self

    def set(self, name, lb):
        self.layers[name] = lb
        return self

    def select(self, context="", entities=None, budget=None):
        b = self.budget if budget is None else int(budget)
        out, used = [], 0
        for c in self.constants:
            if out and used + len(c) > b:
                continue
            out.append(c)
            used += len(c)
        cand = []
        for name, lb in self.layers.items():
            for eid in lb.scan(context, entities):
                e = lb.by_id(eid)
                if e:
                    cand.append((lb.score(context, eid), name, eid, e))
        cand.sort(key=lambda x: (-x[0], x[1], x[2]))
        for _s, _name, _eid, e in cand:
            content = e.get("content", "")
            if out and used + len(content) > b:
                continue
            out.append(content)
            used += len(content)
        return out


if __name__ == "__main__":
    import json
    import sys

    lb = Lorebook.from_world(json.load(open(sys.argv[1])))
    ctx = sys.argv[2] if len(sys.argv) > 2 else "Ия плачет у печи, Марек молчит"
    ids = lb.scan(ctx)
    print("active:", sorted(ids))
    print("select:", lb.select(ctx, budget=600))
    print("schema:", json.dumps(lb.selection_schema(sorted(ids)), ensure_ascii=False))
