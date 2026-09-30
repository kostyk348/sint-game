"""Редактор: самодостаточный HTML содержит мир, свидетелей и граф."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.editor import build_html, graph_data, write_editor  # noqa: E402

WORLD = json.load(open(os.path.join(ROOT, "examples", "lighthouse", "world.json")))


def test_graph_data_has_edges():
    nodes, edges = graph_data(WORLD)
    assert nodes["act"] and nodes["prod"] and edges


def test_build_html_embeds_world_reach_svg():
    html = build_html(WORLD)
    assert "sint-game editor" in html
    assert "<svg" in html
    assert "Скачать world.json" in html
    assert "witness" in html or "не найдена" in html
    # данные мира реально встроены
    assert "journal_found" in html


def test_write_editor(tmp=None):
    import tempfile
    d = tempfile.mkdtemp()
    try:
        out = write_editor(os.path.join(ROOT, "examples", "lighthouse", "world.json"),
                           os.path.join(d, "ed.html"))
        assert os.path.exists(out) and os.path.getsize(out) > 5000
    finally:
        import shutil
        shutil.rmtree(d)


if __name__ == "__main__":
    for fn in [test_graph_data_has_edges, test_build_html_embeds_world_reach_svg, test_write_editor]:
        fn()
        print("ok", fn.__name__)
