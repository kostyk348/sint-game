#!/usr/bin/env python3
"""editor.py — самодостаточный HTML-редактор мира (один файл, без сети и зависимостей).

`sintgame editor world.json -o editor.html` пишет один HTML: обзор, отчёт достижимости
(свидетели), таблица действий, граф зависимостей (флаги/предметы → действия → продукты)
и JSON-вкладка с кнопкой «Скачать world.json». Правки — правкой JSON + экспорт.
"""
import html
import json

from .search import report as reach_report


def _cond_refs(c):
    if not isinstance(c, list) or not c:
        return set()
    op = c[0]
    if op == "flag":
        return {f"flag:{c[1]}"}
    if op == "not":
        return _cond_refs(c[1])
    if op == "has":
        return {f"item:{c[2]}"}
    if op in ("gt", "lt", "ge", "le", "eq") and isinstance(c[1], str) and "." in c[1]:
        return {c[1]}
    if op in ("rel_gt", "rel_lt"):
        return {f"rel:{c[3]}"}
    return set()


def _eff_prods(e):
    if not isinstance(e, list) or not e:
        return set()
    op = e[0]
    if op == "flag" and e[2]:
        return {f"flag:{e[1]}"}
    if op == "set" and "." not in e[1]:
        return {f"flag:{e[1]}"}
    if op == "give":
        return {f"item:{e[2]}"}
    if op == "end":
        return {f"end:{e[1]}"}
    return set()


def graph_data(world):
    nodes = {"req": set(), "act": [], "prod": set()}
    edges = []
    for a in world.get("actions", []):
        rq = set()
        for c in a.get("pre", []) or []:
            rq |= _cond_refs(c)
        pr = set()
        for e in a.get("eff", []) or []:
            pr |= _eff_prods(e)
        nodes["act"].append({"id": a["id"], "label": a.get("label", a["id"]), "req": sorted(rq), "prod": sorted(pr)})
        nodes["req"] |= rq
        nodes["prod"] |= pr
        for r in rq:
            edges.append([r, a["id"]])
        for p in pr:
            edges.append([a["id"], p])
    nodes["req"], nodes["prod"] = sorted(nodes["req"]), sorted(nodes["prod"])
    return nodes, edges


def _svg(world):
    g, _ = graph_data(world)
    reqs, acts, prods = g["req"], g["act"], g["prod"]
    dy, y0 = 24, 30
    h = max(len(reqs), len(acts), len(prods)) * dy + 40
    xr, xa, xp = 20, 320, 640
    pos = {}
    for i, r in enumerate(reqs):
        pos[r] = (xr, y0 + i * dy)
    for i, a in enumerate(acts):
        pos[a["id"]] = (xa, y0 + i * dy)
    for i, p in enumerate(prods):
        pos[p] = (xp, y0 + i * dy)

    def esc(s):
        return html.escape(str(s))

    parts = [f'<svg viewBox="0 0 860 {h}" width="100%" style="max-width:900px">']
    for a in acts:
        ax, ay = pos[a["id"]]
        for r in a["req"]:
            rx, ry = pos[r]
            parts.append(f'<line x1="{rx + 6}" y1="{ry}" x2="{ax - 6}" y2="{ay}" stroke="#7aa2f7" stroke-width="1" opacity="0.5"/>')
        for p in a["prod"]:
            px, py = pos[p]
            parts.append(f'<line x1="{ax + 6}" y1="{ay}" x2="{px - 6}" y2="{py}" stroke="#9ece6a" stroke-width="1" opacity="0.5"/>')
    for r in reqs:
        x, y = pos[r]
        col = "#e0af68" if r.startswith("flag") else ("#7dcfff" if r.startswith("item") else "#bb9af7")
        parts.append(f'<text x="{x}" y="{y + 4}" fill="{col}" font-size="12" font-family="monospace">{esc(r)}</text>')
    for a in acts:
        x, y = pos[a["id"]]
        parts.append(f'<text x="{x}" y="{y + 4}" fill="#c0caf5" font-size="12" font-family="monospace">{esc(a["id"])}</text>')
    for p in prods:
        x, y = pos[p]
        col = "#f7768e" if p.startswith("end") else ("#9ece6a" if p.startswith("flag") else "#7dcfff")
        parts.append(f'<text x="{x}" y="{y + 4}" fill="{col}" font-size="12" font-family="monospace">{esc(p)}</text>')
    parts.append("</svg>")
    return "".join(parts)


_TEMPLATE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>sint-game editor — __TITLE__</title>
<style>
:root{--bg:#1a1b26;--fg:#c0caf5;--dim:#565f89;--acc:#7aa2f7}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 ui-monospace,monospace}
header{padding:16px 20px;border-bottom:1px solid #2f3549}
h1{margin:0;font-size:18px} .dim{color:var(--dim)}
nav{display:flex;gap:4px;padding:8px 20px;border-bottom:1px solid #2f3549;flex-wrap:wrap}
nav button{background:#24283b;color:var(--fg);border:1px solid #2f3549;padding:6px 12px;cursor:pointer;border-radius:6px}
nav button.active{background:var(--acc);color:#1a1b26;border-color:var(--acc)}
section{display:none;padding:16px 20px} section.active{display:block}
table{border-collapse:collapse;width:100%} td,th{border:1px solid #2f3549;padding:4px 8px;text-align:left;font-size:13px}
th{background:#24283b} .ok{color:#9ece6a} .bad{color:#f7768e} .warn{color:#e0af68}
textarea{width:100%;height:60vh;background:#16161e;color:var(--fg);border:1px solid #2f3549;padding:10px;font:13px/1.4 ui-monospace,monospace}
button.act{background:var(--acc);color:#1a1b26;border:0;padding:8px 14px;border-radius:6px;cursor:pointer;margin-top:8px}
code{color:#e0af68}
</style></head><body>
<header>
  <h1>sint-game editor — <span id="title"></span></h1>
  <div class="dim" id="summary"></div>
</header>
<nav>
  <button data-tab="overview" class="active">Обзор</button>
  <button data-tab="reach">Достижимость</button>
  <button data-tab="actions">Действия</button>
  <button data-tab="graph">Граф</button>
  <button data-tab="json">JSON</button>
</nav>
<section id="overview" class="active"></section>
<section id="reach"></section>
<section id="actions"></section>
<section id="graph">__SVG__<p class="dim">флаги/предметы (слева) → действия (центр) → флаги/предметы/концовки (справа)</p></section>
<section id="json">
  <p class="dim">Правьте JSON и скачайте. Проверить локально: <code>sintgame validate world.json</code></p>
  <textarea id="jsonArea"></textarea><br>
  <button class="act" id="dl">Скачать world.json</button>
</section>
<script>
const WORLD = __WORLD__; const REACH = __REACH__;
const $ = s => document.querySelector(s);
document.querySelectorAll("nav button").forEach(b => b.onclick = () => {
  document.querySelectorAll("nav button").forEach(x => x.classList.remove("active"));
  document.querySelectorAll("section").forEach(x => x.classList.remove("active"));
  b.classList.add("active"); $("#" + b.dataset.tab).classList.add("active");
});
$("#title").textContent = WORLD.title || "(без названия)";
const nEnt = Object.keys(WORLD.entities || {}).length;
$("#summary").textContent = `сущностей: ${nEnt} · действий: ${(WORLD.actions||[]).length} · концовок: ${(REACH.declared||[]).length}`;
// overview
const ends = REACH.reachable || {};
$("#overview").innerHTML = "<h3>Концовки</h3><table><tr><th>концовка</th><th>свидетель</th></tr>" +
  (REACH.declared||[]).map(e => `<tr><td>${e}</td><td>${(ends[e]||[]).map(x=>`<code>${x}</code>`).join(" → ") || '<span class="bad">не найдена</span>'}</td></tr>`).join("") +
  "</table>";
// reach
let rh = `<p>состояний исследовано: ${REACH.states_explored} · исчерпано: ${REACH.exhausted?'да':'нет'}</p>`;
if((REACH.unreachable||[]).length) rh += `<p class="bad">недостижимо (доказано): ${REACH.unreachable.join(", ")}</p>`;
if((REACH.not_found||[]).length) rh += `<p class="warn">не найдено (не доказано): ${REACH.not_found.join(", ")}</p>`;
if((REACH.dead_ends||[]).length) rh += `<p class="warn">тупики: ${(REACH.dead_ends||[]).length}</p>`;
$("#reach").innerHTML = rh;
// actions
$("#actions").innerHTML = "<table><tr><th>id</th><th>label</th><th>pre</th><th>eff</th></tr>" +
  (WORLD.actions||[]).map(a => `<tr><td><code>${a.id}</code></td><td>${a.label||""}</td><td><code>${JSON.stringify(a.pre||[])}</code></td><td><code>${JSON.stringify(a.eff||[])}</code></td></tr>`).join("") + "</table>";
// json
$("#jsonArea").value = JSON.stringify(WORLD, null, 2);
$("#dl").onclick = () => {
  try { const w = JSON.parse($("#jsonArea").value);
    const blob = new Blob([JSON.stringify(w, null, 2)], {type:"application/json"});
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = (w.title||"world") + ".json"; a.click();
  } catch(e) { alert("JSON невалиден: " + e.message); }
};
</script></body></html>
"""


def build_html(world, reach=None):
    reach = reach if reach is not None else reach_report(world)[1]
    def safe(o):
        return json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    return (_TEMPLATE
            .replace("__TITLE__", html.escape(str(world.get("title", ""))))
            .replace("__SVG__", _svg(world))
            .replace("__WORLD__", safe(world))
            .replace("__REACH__", safe(reach)))


def write_editor(world_path, out_path=None):
    world = json.load(open(world_path))
    out = out_path or (world_path.rsplit(".", 1)[0] + ".editor.html")
    open(out, "w").write(build_html(world))
    return out
