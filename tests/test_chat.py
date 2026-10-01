"""Персонажный чат: префикс персоны, карточки из мира, оффлайн-ответ."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame import chat  # noqa: E402

WORLD = json.load(open(os.path.join(ROOT, "examples", "campaign", "world.json")))


def test_persona_prefix_is_stable_and_has_voice():
    c = {"name": "Лея", "persona": "знахарка", "voice": "неторопливо"}
    p1, p2 = chat.persona_prefix(c), chat.persona_prefix(c)
    assert p1 == p2 and "неторопливо" in p1 and "Лея" in p1


def test_characters_from_world_excludes_player():
    chars = chat.characters_from_world(WORLD)
    ids = [c["name"] for c in chars]
    assert "player" not in ids
    assert len(chars) >= 1


def test_reply_offline_returns_stub():
    c = {"name": "Лея", "persona": "знахарка", "voice": "неторопливо"}
    assert chat.reply(c, "привет", [], []) == "(нет ответа — LLM недоступен)"


if __name__ == "__main__":
    for fn in [test_persona_prefix_is_stable_and_has_voice, test_characters_from_world_excludes_player,
               test_reply_offline_returns_stub]:
        fn()
        print("ok", fn.__name__)
