#!/usr/bin/env python3
"""memory.py — долгая память игры: факты о мире + голоса персонажей.

Короткое окно `--context` помнит несколько ходов. Для игры на 50+ ходов нужна ДЛИННАЯ
память, но класть всю историю в промпт нельзя (растут токены и ломается prompt-cache).
Решение — накопление фактов + извлечение только РЕЛЕВАНТНЫХ текущей сцене (по сущностям).
"""
import re


def _tokens(s):
    return set(re.findall(r"[0-9a-zA-Zа-яА-ЯёЁ_]+", (s or "").lower()))


class FactLog:
    """Накапливает факты хода; отдаёт релевантные текущим сущностям (bounded prompt)."""

    def __init__(self, max_facts=500):
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
