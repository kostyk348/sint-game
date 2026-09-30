"""Компакция: сворачивание admitted-действий (.ext.json) в мир + перевалидация."""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.compact import compact  # noqa: E402

WORLD = json.load(open(os.path.join(ROOT, "examples", "lighthouse", "world.json")))

VALID = {"id": "hug_iya", "label": "Обнять Ию",
         "pre": [["not", ["flag", "iya_hugged"]]],
         "eff": [["heal", "iya", 3], ["flag", "iya_hugged", 1]]}
DANGLING = {"id": "bad", "label": "плохое",
            "pre": [["flag", "never_set_flag"]], "eff": [["flag", "foo", 1]]}
DUP = {"id": "talk_iya", "label": "дубликат", "pre": [], "eff": [["say", "x"]]}


def _setup(ext):
    d = tempfile.mkdtemp()
    wp = os.path.join(d, "w.json")
    json.dump(WORLD, open(wp, "w"), ensure_ascii=False)
    if ext is not None:
        json.dump(ext, open(wp + ".ext.json", "w"), ensure_ascii=False)
    return d, wp


def test_compact_folds_valid():
    d, wp = _setup([VALID])
    try:
        w2, info = compact(wp)
        assert w2 is not None, info
        assert any(a["id"] == "hug_iya" for a in w2["actions"])
        assert not os.path.exists(wp + ".ext.json")  # свернули на месте -> ext убран
    finally:
        shutil.rmtree(d)


def test_compact_skips_duplicates():
    d, wp = _setup([DUP])
    try:
        w2, info = compact(wp)
        assert w2 is not None
        assert any("duplicates_skipped=1" in x for x in info)
    finally:
        shutil.rmtree(d)


def test_compact_rejects_broken_ext():
    d, wp = _setup([DANGLING])
    try:
        w2, info = compact(wp)
        assert w2 is None and any("dangling" in e for e in info)
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    for fn in [test_compact_folds_valid, test_compact_skips_duplicates, test_compact_rejects_broken_ext]:
        fn()
        print("ok", fn.__name__)
