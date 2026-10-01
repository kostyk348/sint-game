"""Долгая память: сохранение/загрузка фактов+истории+состояния между сессиями."""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.memory import FactLog, load_session, save_session  # noqa: E402


def test_factlog_roundtrip_and_relevance():
    fl = FactLog()
    fl.add(1, "Марек отвернулся к стеклу", ["marek"])
    fl.add(2, "Ия плачет у печи", ["iya"])
    fl2 = FactLog.from_list(fl.to_list())
    assert fl2.to_list() == fl.to_list()
    assert fl2.relevant(["marek"]) == ["Марек отвернулся к стеклу"]


def test_session_roundtrip():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "s.json")
        state = {"flags": {"a": 1}, "attrs": {}, "holds": [], "rel": {}, "done": [], "ended": None}
        mem = [{"turn": 1, "text": "факт", "entities": ["a"]}]
        save_session(p, state, mem, ["Действие"], 3, "Мир")
        s = load_session(p)
        assert s["state"] == state and s["turn"] == 3 and s["world"] == "Мир"
        assert s["memory"][0]["text"] == "факт" and s["history"] == ["Действие"]
    finally:
        shutil.rmtree(d)


def test_session_accepts_old_raw_state():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "old.json")
        json.dump({"flags": {}, "ended": None}, open(p, "w"))
        s = load_session(p)
        assert s["memory"] == [] and s["turn"] == 0
        assert s["state"] == {"flags": {}, "ended": None}
    finally:
        shutil.rmtree(d)


if __name__ == "__main__":
    for fn in [test_factlog_roundtrip_and_relevance, test_session_roundtrip,
               test_session_accepts_old_raw_state]:
        fn()
        print("ok", fn.__name__)
