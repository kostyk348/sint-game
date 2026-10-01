#!/usr/bin/env python3
"""memory.py — долгая память игры: факты + голоса + СОХРАНЕНИЕ МЕЖДУ СЕССИЯМИ.

Короткое окно `--context` помнит несколько ходов. Для РПГ-кампании нужна память, которая
живёт МЕЖДУ запусками: факты, история и состояние сериализуются вместе в один файл сейва.
В промпт попадают только РЕЛЕВАНТНЫЕ текущей сцене факты — промпт не растёт.
"""
import json
import os
import re

SESSION_VERSION = 1


def _tokens(s):
    return set(re.findall(r"[0-9a-zA-Zа-яА-ЯёЁ_]+", (s or "").lower()))


class FactLog:
    """Накапливает факты хода; отдаёт релевантные текущим сущностям (bounded prompt)."""

    def __init__(self, max_facts=2000):
        self.facts = []
        self.max_facts = max_facts

    def add(self, turn, text, entities):
        if not text:
            return
        self.facts.append({"turn": int(turn), "text": text, "entities": sorted(set(entities))})
        if len(self.facts) > self.max_facts:
            self.facts = self.facts[-self.max_facts:]

    def relevant(self, entities, k=6):
        q = set(entities)
        if not q:
            return []
        scored = []
        for f in self.facts:
            ov = len(q & set(f["entities"]))
            if ov:
                scored.append((ov, f["turn"], f["text"]))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [t for _, _, t in scored[:k]]

    def to_list(self):
        return list(self.facts)

    @classmethod
    def from_list(cls, items, max_facts=2000):
        fl = cls(max_facts=max_facts)
        for it in items or []:
            if isinstance(it, dict) and "text" in it:
                fl.facts.append({"turn": int(it.get("turn", 0)),
                                 "text": str(it["text"]),
                                 "entities": list(it.get("entities") or [])})
            elif isinstance(it, str):
                fl.facts.append({"turn": 0, "text": it, "entities": []})
        return fl

    def dump(self):
        return list(self.facts)


def voices_of(world, entities):
    """Голоса упомянутых персонажей (для консистентности прозы)."""
    out = {}
    for i in entities:
        v = (world.get("entities", {}).get(i) or {}).get("voice")
        if v:
            out[i] = v
    return out


# --- долгая память между сессиями ---------------------------------------------------

def save_session(path, state, memory, history, turn, world_title=""):
    """Сохранить ВСЁ: состояние ядра + факты + историю. Ядро можно продолжить побитово."""
    data = {"version": SESSION_VERSION, "world": world_title, "turn": int(turn),
            "state": state, "memory": memory or [], "history": history or []}
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    json.dump(data, open(path, "w"), ensure_ascii=False, indent=2)
    return path


def load_session(path):
    """Загрузить сессию. Совместимо со старым форматом (сырой state без обёртки)."""
    d = json.load(open(path))
    if isinstance(d, dict) and "state" in d:
        d.setdefault("memory", [])
        d.setdefault("history", [])
        d.setdefault("turn", 0)
        d.setdefault("world", "")
        return d
    return {"version": SESSION_VERSION, "world": "", "turn": 0,
            "state": d, "memory": [], "history": []}
