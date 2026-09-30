#!/usr/bin/env python3
"""prompt.py — сборка промптов со СТАБИЛЬНЫМ ПРЕФИКСОМ под prompt-cache провайдера.

Провайдер кэширует KV только для БАЙТ-ИДЕНТИЧНОГО префикса. Поэтому:

  [ PREFIX ]  одинаковый КАЖДЫЙ вызов   -> попадание в кэш, дешево и быстро
  --- граница кэша ---
  [ SUFFIX ]  всё изменяемое             -> состояние, меню, дельта, ввод, admitted-действия

ЗАКОН: ничего изменяемого (состояние, время, соль, рантайм-действия) НЕ ставить
выше границы — иначе кэш нейронки холодный на каждом вызове.

Ключевая тонкость: если засунуть в префикс ВЕСЬ world JSON (с actions), то каждое
принятое в рантайме действие меняет префикс и ломает кэш. Поэтому префикс — только
НЕИЗМЕНЯЕМАЯ часть мира (схема + тон + статичные описания сущностей).
"""
import hashlib
import json

from .schema import SCHEMA_TEXT

SYSTEM = (
    "Ты — часть детерминированного текстового игрового движка.\n"
    "Правило №1: состояние мира меняется только данными (JSON), не словами.\n"
    "Правило №2: не выдумывай чисел и фактов, которых нет во входных данных.\n"
    "Правило №3: отвечай ровно в запрошенном формате.\n"
)

BOUNDARY = "\n---8<--- CACHE BOUNDARY ---8<---\n"

# статичные поля сущности (attrs изменяются -> идут в suffix, не сюда)
_STATIC_FIELDS = ("type", "tags", "desc")


def world_bible(world):
    """НЕИЗМЕНЯЕМЫЙ префикс: не меняется ни от хода, ни от admitted-действий."""
    ents = {i: {k: v for k, v in e.items() if k in _STATIC_FIELDS}
            for i, e in world.get("entities", {}).items()}
    return (SYSTEM
            + "\n=== СХЕМА ===\n" + SCHEMA_TEXT
            + "\n=== МИР ===\n" + str(world.get("title", ""))
            + "\nТОН: " + str(world.get("tone", ""))
            + "\n=== СУЩНОСТИ (статично) ===\n"
            + json.dumps(ents, ensure_ascii=False, sort_keys=True))


def build(prefix, suffix):
    return prefix + BOUNDARY + suffix


def prefix_hash(prefix):
    return hashlib.sha1(prefix.encode()).hexdigest()[:12]


class PrefixMonitor:
    """Следит за стабильностью префикса между вызовами (рушится -> кэш промах)."""

    def __init__(self):
        self.last = None
        self.hits = 0
        self.misses = 0

    def note(self, prefix):
        h = prefix_hash(prefix)
        if h == self.last:
            self.hits += 1
        else:
            self.misses += 1
        self.last = h
        return h

    def report(self):
        total = self.hits + self.misses
        rate = (self.hits / total) if total else 0.0
        return f"prefix-stability: {self.hits}/{total} ({rate:.0%}), last={self.last}"


# Демонстрация стабильности префикса — в tests/test_prompt_cache.py

