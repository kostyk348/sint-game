"""Веб-РПГ: функции сервера (новая игра, ход, save/load) без поднятия сокета."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame import serve  # noqa: E402

WP = os.path.join(ROOT, "examples", "lighthouse", "world.json")


def test_rpg_flow():
    g = serve.rpg_new(WP)
    assert g["session"] and g["actions"] and g["title"]
    r = serve.rpg_act(g["session"], g["actions"][0]["id"])
    assert r.get("error") is None and r["turn"] == 1
    assert serve.rpg_save(g["session"])["ok"] is True
    l = serve.rpg_load(WP)
    assert l["loaded"] is True and int(l["turn"]) >= 1


def test_rpg_act_rejects_unknown_action():
    g = serve.rpg_new(WP)
    r = serve.rpg_act(g["session"], "no_such_action")
    assert "error" in r


def test_rpg_worlds_listed():
    assert len(serve._default_worlds()) >= 2


if __name__ == "__main__":
    for fn in [test_rpg_flow, test_rpg_act_rejects_unknown_action, test_rpg_worlds_listed]:
        fn()
        print("ok", fn.__name__)
