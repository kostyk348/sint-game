"""Интент: оффлайн-фолбэк и сопоставление с существующими действиями (без LLM)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame import intent as I  # noqa: E402
from sintgame.kernel import World  # noqa: E402

WORLD = json.load(open(os.path.join(ROOT, "examples", "lighthouse", "world.json")))


def _w():
    return World(json.loads(json.dumps(WORLD)))


def test_match_existing_hits_known_action():
    w = _w()
    intent = {"verb": "поговорить", "target": "iya", "manner": "", "known_action": None}
    assert I.match_existing(WORLD, "поговорить с Ией", intent, w) == "talk_iya"


def test_match_existing_none_for_novel():
    w = _w()
    intent = {"verb": "обнять", "target": "iya", "manner": "ласково", "known_action": None}
    assert I.match_existing(WORLD, "обнять Ию", intent, w) is None


def test_parse_intent_offline_fallback():
    w = _w()
    intent = I.parse_intent("погладить кота", WORLD, w)  # LLM недоступен
    assert intent.get("verb")  # фолбэк вернул осмысленный dict, а не падение


def test_pipeline_offline_resolves_known():
    w = _w()
    aid, note, admitted = I.pipeline("поговорить с Ией", WORLD, w)
    assert aid == "talk_iya" and admitted is None


def test_pipeline_offline_no_crash_on_novel():
    w = _w()
    aid, note, admitted = I.pipeline("станцевать джигу на столе", WORLD, w)
    assert aid is None and admitted is None  # не падаем, честно отказываем


if __name__ == "__main__":
    for fn in [test_match_existing_hits_known_action, test_match_existing_none_for_novel,
               test_parse_intent_offline_fallback, test_pipeline_offline_resolves_known,
               test_pipeline_offline_no_crash_on_novel]:
        fn()
        print("ok", fn.__name__)
