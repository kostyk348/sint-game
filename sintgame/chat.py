#!/usr/bin/env python3
"""chat.py — персонажный чат (в духе character.ai) на кирпичах движка.

Отличие от игрового режима: нет правил и действий, есть ПЕРСОНА и ПАМЯТЬ. «Состояние» —
история диалога + факты. Персона — стабильный префикс (prompt-cache не ломается),
история/реплика — суффикс.
"""
import json
import os

from . import prompt as P
from .gen import gen_text

SYSTEM = (
    "Ты — персонаж чата. Отвечай В РОЛИ, от первого лица, живо и по-человечески, коротко. "
    "Не выходи из роли, не говори о себе в третьем лице, не добавляй пояснений и служебных "
    "пометок. Помни сказанное ранее. Если что-то неизвестно — реагируй в характере, не "
    "выдумывай лишних фактов о мире."
)


def persona_prefix(char):
    parts = [SYSTEM,
             f"\nИМЯ: {char.get('name', '')}",
             f"\nРОЛЬ/ЛИЧНОСТЬ: {char.get('persona', '')}",
             f"\nГОЛОС: {char.get('voice', '')}"]
    if char.get("desc"):
        parts.append(f"\nВНЕШНОСТЬ: {char['desc']}")
    if char.get("example"):
        parts.append(f"\nПРИМЕР РЕЧИ: {char['example']}")
    return "".join(parts)


def reply(char, message, history, facts, max_turns=8):
    """Один ответ персонажа. history — список строк 'Кто: что'; facts — память."""
    hist = "\n".join(history[-2 * max_turns:]) if history else ""
    mem = " | ".join(facts or [])
    suffix = ""
    if mem:
        suffix += f"ПАМЯТЬ (ранее установленное): {mem}\n"
    if hist:
        suffix += f"ДИАЛОГ:\n{hist}\n"
    suffix += f"Пользователь: {message}\n{char.get('name', 'Персонаж')}:"
    txt = gen_text(P.build(persona_prefix(char), suffix)).strip()
    return txt or "(нет ответа — LLM недоступен)"


def characters_from_world(world, title=None):
    """NPC мира → карточки персонажей (id, name, persona, voice)."""
    out = []
    t = title or world.get("title", "мир")
    for eid, e in (world.get("entities") or {}).items():
        if "player" in (e.get("tags") or []):
            continue
        if "npc" in (e.get("tags") or []) or e.get("voice"):
            out.append({"id": f"{t}#{eid}", "name": eid,
                        "persona": e.get("desc", ""), "voice": e.get("voice", ""),
                        "desc": e.get("desc", "")})
    return out


def load_character_dir(d):
    out = []
    if not d or not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            try:
                c = json.load(open(os.path.join(d, fn)))
            except Exception:
                continue
            c.setdefault("id", fn[:-5])
            out.append(c)
    return out
