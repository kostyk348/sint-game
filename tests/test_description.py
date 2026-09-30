"""Описание: проза подхватывает описания упомянутых сущностей (контекст)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.play import _mentioned  # noqa: E402


def test_mentioned_extracts_desc_of_referenced_entity():
    world = {"entities": {"iya": {"desc": "девочка Ия"}, "marek": {"desc": "смотритель"}}}
    assert _mentioned(world, ["Ия плачет"], ["iya.trust: 0 -> 10"]) == {"iya": "девочка Ия"}


def test_mentioned_empty_when_nothing_referenced():
    world = {"entities": {"iya": {"desc": "девочка"}}}
    assert _mentioned(world, ["тишина"], ["player.cold: 1 -> 2"]) == {}


if __name__ == "__main__":
    for fn in [test_mentioned_extracts_desc_of_referenced_entity, test_mentioned_empty_when_nothing_referenced]:
        fn()
        print("ok", fn.__name__)
