#!/usr/bin/env python3
"""serve.py — локальный веб-интерфейс: РПГ (главное) + персонажный чат (вторично).

Только стандартная библиотека: http.server + встроенный HTML.
  GET  /                 — РПГ: выбор мира, состояние, действия, свободный ввод, save/load
  GET  /chat             — персонажный чат
  GET  /api/rpg/worlds   — список миров
  POST /api/rpg/new      {world}                     — новая игра
  POST /api/rpg/act      {session, action|text}      — ход (действие из меню или свободный текст)
  POST /api/rpg/save     {session}                   — сохранить (долгая память)
  POST /api/rpg/load     {world}                     — загрузить последнюю сессию мира
  GET  /api/characters, POST /api/chat, GET /api/health
"""
import json
import os
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import chat
from . import intent as I
from . import memory as M
from .cache import path as cache_path
from .kernel import World, diff
from .play import _referenced_ids, gen_prose, load_cache, load_world

CHARACTERS = {}
SESSIONS = {}   # чат: sid -> {history, facts}
RPG = {}        # РПГ: sid -> {path, world, w, flog, history, monitor, seed}
CONTEXT = 4
CACHE = load_cache()
MONITOR = None


def _default_worlds():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ex = os.path.join(root, "examples")
    out = []
    if os.path.isdir(ex):
        for d in sorted(os.listdir(ex)):
            p = os.path.join(ex, d, "world.json")
            if os.path.exists(p):
                out.append(p)
    return out


def _slug(path):
    return os.path.basename(os.path.dirname(os.path.abspath(path))) or "world"


def _session_file(world_path):
    return cache_path(f"rpg_{_slug(world_path)}.json")


def load_characters(worlds=None, character_dir=None):
    CHARACTERS.clear()
    for wp in (worlds or _default_worlds()):
        try:
            w = json.load(open(wp))
        except Exception:
            continue
        for c in chat.characters_from_world(w):
            CHARACTERS[c["id"]] = c
    for c in chat.load_character_dir(character_dir):
        CHARACTERS[c["id"]] = c
    return CHARACTERS


def _rpg_payload(sid):
    s = RPG[sid]
    w = s["w"]
    return {"session": sid, "title": s["world"].get("title", ""),
            "state": w.status(), "ended": w.ended, "turn": s["turn"],
            "actions": [{"id": a["id"], "label": a["label"]} for a in w.available()],
            "has_save": os.path.exists(_session_file(s["path"]))}


def rpg_new(world_path, seed=None):
    world = load_world(world_path)
    w = World(world, seed=seed) if seed is not None else World(world)
    sid = "rpg-" + os.urandom(4).hex()
    from . import prompt as _P
    RPG[sid] = {"path": world_path, "world": world, "w": w, "flog": M.FactLog(),
                "mem": M.layering(world),
                "history": [], "monitor": _P.PrefixMonitor(), "turn": 0,
                "seed": w.rng.randint(0, 1 << 30)}
    return _rpg_payload(sid)


def rpg_act(sid, action_id=None, text=None):
    s = RPG.get(sid)
    if not s:
        return {"error": "нет такой сессии"}
    world, w, flog, history = s["world"], s["w"], s["flog"], s["history"]
    note = None
    if w.ended:
        return {"error": "игра окончена", "ended": w.ended}
    if text and not action_id:
        action_id, note, _ = I.pipeline(text, world, w)
        if not action_id:
            return {"error": note or "не понял действие", "note": note,
                    "actions": [{"id": a["id"], "label": a["label"]} for a in w.available()]}
    if not action_id or not w.can(action_id):
        return {"error": f"действие '{action_id}' недоступно",
                "actions": [{"id": a["id"], "label": a["label"]} for a in w.available()]}
    before = w.snapshot()
    label = next((a["label"] for a in world["actions"] if a["id"] == action_id), action_id)
    said = w.act(action_id)
    d = diff(before, w.snapshot())
    ids = _referenced_ids(world, said, d)
    facts = s["mem"].set("saga", M.saga_layer(flog.facts)).select(" ".join(said + d), ids, budget=600)
    prose, _src = gen_prose(world, world.get("tone", "neutral"), label, said, d, CACHE, True,
                            False, s["monitor"], history[-CONTEXT:] if CONTEXT else [], facts)
    history.append(label)
    if said or d:
        flog.add(len(history), " ".join(said) if said else label, ids)
    s["turn"] = len(history)
    out = _rpg_payload(sid)
    out.update({"prose": prose, "said": said, "delta": d, "label": label, "note": note,
                "facts": len(flog.facts)})
    return out


def rpg_save(sid):
    s = RPG.get(sid)
    if not s:
        return {"error": "нет такой сессии"}
    p = _session_file(s["path"])
    M.save_session(p, s["w"].state(), s["flog"].to_list(), s["history"],
                   s["turn"], s["world"].get("title", ""))
    return {"ok": True, "path": p, "turn": s["turn"], "facts": len(s["flog"].facts)}


def rpg_load(world_path):
    p = _session_file(world_path)
    if not os.path.exists(p):
        return {"error": "сохранения нет"}
    sess = M.load_session(p)
    sid = rpg_new(world_path, seed=1)["session"]
    s = RPG[sid]
    s["w"].restore(sess["state"])
    s["flog"] = M.FactLog.from_list(sess.get("memory"))
    s["history"] = list(sess.get("history") or [])
    s["turn"] = int(sess.get("turn", 0))
    out = _rpg_payload(sid)
    out.update({"loaded": True, "facts": len(s["flog"].facts)})
    return out


RPG_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>sint-game · РПГ</title>
<style>
:root{--bg:#1a1b26;--fg:#c0caf5;--dim:#565f89;--acc:#7aa2f7;--bg2:#24283b;--ok:#9ece6a}
*{box-sizing:border-box}
body{margin:0;height:100vh;display:flex;flex-direction:column;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,sans-serif}
header{display:flex;gap:10px;align-items:center;padding:10px 16px;border-bottom:1px solid #2f3549;flex-wrap:wrap}
select,input,button{background:#16161e;color:var(--fg);border:1px solid #2f3549;border-radius:8px;padding:8px 10px;font:inherit}
button{background:var(--acc);color:#1a1b26;border:0;cursor:pointer;font-weight:600}
button.sec{background:var(--bg2);color:var(--fg)}
#state{color:var(--dim);font-size:13px}
#log{flex:1;overflow:auto;padding:18px;display:flex;flex-direction:column;gap:12px}
.ev{border-left:2px solid #2f3549;padding-left:12px}
.ev .lbl{color:var(--acc);font-size:13px}
.ev .say{color:var(--dim);font-size:13px}
.ev .d{color:var(--ok);font-size:13px}
.ev .prose{white-space:pre-wrap}
#acts{padding:8px 16px;display:flex;flex-wrap:wrap;gap:6px}
#acts button{background:var(--bg2);color:var(--fg);font-weight:400;font-size:14px}
#bar{display:flex;gap:8px;padding:10px 16px;border-top:1px solid #2f3549}
#bar input{flex:1}
.msg{color:#f7768e}
</style></head><body>
<header>
  <select id="world"></select>
  <button id="new">Новая игра</button>
  <button class="sec" id="load">Загрузить</button>
  <button class="sec" id="save">Сохранить</button>
  <span id="state"></span>
</header>
<div id="log"></div>
<div id="acts"></div>
<div id="bar"><input id="in" placeholder="или напиши своими словами…" autocomplete="off"><button id="send">Сказать</button></div>
<script>
const $=s=>document.querySelector(s); let SID=null, BUSY=false;
async function jget(u){return (await fetch(u)).json()}
async function jpost(u,b){return (await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})})).json()}
async function worlds(){ const ws=await jget('/api/rpg/worlds'); $('#world').innerHTML=ws.map(w=>`<option value="${w.path}">${w.title} (${w.actions} действий)</option>`).join(''); }
function logHtml(e){
  const parts=[`<div class="ev"><div class="lbl">▸ ${e.label||''}</div>`];
  if(e.said&&e.said.length) parts.push(`<div class="say">${(e.said||[]).join('<br>')}</div>`);
  if(e.delta&&e.delta.length) parts.push(`<div class="d">[${e.delta.join('; ')}]</div>`);
  if(e.prose) parts.push(`<div class="prose">${e.prose}</div>`);
  if(e.ended) parts.push(`<div class="lbl">КОНЦОВКА: ${e.ended}</div>`);
  parts.push('</div>'); return parts.join('');
}
function render(p){ if(p.error){ $('#log').insertAdjacentHTML('beforeend',`<div class="msg">${p.error}</div>`); return; }
  if(p.state!==undefined) $('#state').textContent=p.state+(p.ended?` · концовка ${p.ended}`:'');
  if(p.title) $('#state').textContent=(p.state||'')+(p.ended?` · концовка ${p.ended}`:'');
  $('#acts').innerHTML=(p.actions||[]).map(a=>`<button data-id="${a.id}">${a.label}</button>`).join('');
  document.querySelectorAll('#acts button').forEach(b=>b.onclick=()=>act({action:b.dataset.id}));
}
async function newGame(){ const r=await jpost('/api/rpg/new',{world:$('#world').value}); if(r.error) return render(r); SID=r.session; $('#log').innerHTML=''; render(r); }
async function act(body){ if(!SID||BUSY) return; BUSY=true; body.session=SID; const r=await jpost('/api/rpg/act',body); BUSY=false;
  if(r.error){ render(r); return; } $('#log').insertAdjacentHTML('beforeend',logHtml(r)); $('#log').scrollTop=$('#log').scrollHeight; render(r); }
$('#new').onclick=newGame;
$('#save').onclick=async()=>{ if(!SID)return; const r=await jpost('/api/rpg/save',{session:SID}); $('#log').insertAdjacentHTML('beforeend',`<div class="msg">${r.error||('сохранено: '+r.path+' · ход '+r.turn+' · фактов '+r.facts)}</div>`); };
$('#load').onclick=async()=>{ const r=await jpost('/api/rpg/load',{world:$('#world').value}); if(r.error) return render(r); SID=r.session; $('#log').innerHTML=`<div class="ev"><div class="lbl">загружено · ход ${r.turn} · фактов ${r.facts}</div></div>`; render(r); };
$('#send').onclick=()=>{ const t=$('#in').value.trim(); if(!t)return; $('#in').value=''; act({text:t}); };
$('#in').onkeydown=e=>{ if(e.key==='Enter'){ e.preventDefault(); $('#send').click(); } };
worlds();
</script></body></html>"""

CHAT_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>sint-game · чат</title>
<style>
:root{--bg:#1a1b26;--fg:#c0caf5;--dim:#565f89;--acc:#7aa2f7;--bg2:#24283b}
*{box-sizing:border-box}
body{margin:0;height:100vh;display:flex;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
aside{width:250px;border-right:1px solid #2f3549;padding:12px;overflow:auto}
aside h2{font-size:12px;color:var(--dim);text-transform:uppercase;margin:0 0 8px}
.char{padding:8px 10px;border-radius:8px;cursor:pointer;margin-bottom:4px}
.char:hover{background:var(--bg2)} .char.sel{background:var(--acc);color:#1a1b26}
main{flex:1;display:flex;flex-direction:column;min-width:0}
header{padding:10px 16px;border-bottom:1px solid #2f3549} header b{font-size:16px}
#log{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.msg{max-width:70%;padding:10px 14px;border-radius:12px;white-space:pre-wrap}
.me{align-self:flex-end;background:var(--acc);color:#1a1b26}
.bot{align-self:flex-start;background:var(--bg2)}
form{display:flex;gap:8px;padding:12px 16px;border-top:1px solid #2f3549}
input{flex:1;background:#16161e;color:var(--fg);border:1px solid #2f3549;border-radius:8px;padding:10px 12px;font:inherit}
button{background:var(--acc);color:#1a1b26;border:0;border-radius:8px;padding:10px 18px;font:inherit;cursor:pointer}
</style></head><body>
<aside><h2>Персонажи</h2><div id="chars"></div><p style="color:#565f89;font-size:12px"><a href="/" style="color:#7aa2f7">← к РПГ</a></p></aside>
<main><header><b id="cname">—</b></header><div id="log"></div>
<form id="f"><input id="in" placeholder="Написать…" autocomplete="off" autofocus><button>Отправить</button></form></main>
<script>
let CHARS=[],CUR=null,HIST=[],SID="local-"+Math.random().toString(36).slice(2,8);
const $=s=>document.querySelector(s);
async function loadChars(){CHARS=await(await fetch('/api/characters')).json();
 $('#chars').innerHTML=CHARS.map(c=>`<div class="char" data-id="${c.id}">${c.name}</div>`).join('')||'нет';
 document.querySelectorAll('.char').forEach(el=>el.onclick=()=>select(el.dataset.id)); if(CHARS[0])select(CHARS[0].id);}
function select(id){CUR=CHARS.find(c=>c.id===id);$('#cname').textContent=CUR.name;$('#log').innerHTML='';document.querySelectorAll('.char').forEach(e=>e.classList.toggle('sel',e.dataset.id===id));}
function add(cls,t){const d=document.createElement('div');d.className='msg '+cls;d.textContent=t;$('#log').appendChild(d);$('#log').scrollTop=$('#log').scrollHeight;}
$('#f').onsubmit=async e=>{e.preventDefault();const m=$('#in').value.trim();if(!m||!CUR)return;add('me',m);$('#in').value='';
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({character:CUR.id,message:m,session:SID})});
 add('bot',(await r.json()).reply);};
loadChars();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", code)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(RPG_HTML.encode(), "text/html; charset=utf-8")
        elif self.path == "/chat":
            self._send(CHAT_HTML.encode(), "text/html; charset=utf-8")
        elif self.path == "/api/rpg/worlds":
            out = []
            for p in _default_worlds():
                try:
                    w = json.load(open(p))
                    out.append({"path": p, "title": w.get("title", os.path.basename(p)),
                                "actions": len(w.get("actions", []))})
                except Exception:
                    pass
            self._json(out)
        elif self.path == "/api/characters":
            self._json(list(CHARACTERS.values()))
        elif self.path == "/api/health":
            self._json({"ok": True, "characters": len(CHARACTERS), "rpg_sessions": len(RPG)})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        b = self._body()
        if self.path == "/api/rpg/new":
            return self._json(rpg_new(b.get("world") or _default_worlds()[0]))
        if self.path == "/api/rpg/act":
            return self._json(rpg_act(b.get("session"), b.get("action"), b.get("text")))
        if self.path == "/api/rpg/save":
            return self._json(rpg_save(b.get("session")))
        if self.path == "/api/rpg/load":
            return self._json(rpg_load(b.get("world") or _default_worlds()[0]))
        if self.path == "/api/chat":
            cid = b.get("character")
            char = CHARACTERS.get(cid) or next(iter(CHARACTERS.values()), None)
            if not char:
                return self._json({"error": "no characters"}, 400)
            msg = str(b.get("message", ""))[:4000]
            st = SESSIONS.setdefault(b.get("session", "default"), {"history": [], "facts": []})
            text = chat.reply(char, msg, st["history"], st["facts"])
            name = char.get("name", "Персонаж")
            st["history"].append(f"Пользователь: {msg}")
            st["history"].append(f"{name}: {text}")
            st["history"] = st["history"][-40:]
            if len(msg) > 15:
                st["facts"].append(msg.strip())
            st["facts"] = st["facts"][-20:]
            return self._json({"reply": text, "character": name})
        return self._json({"error": "not found"}, 404)

    def log_message(self, format, *args):
        pass


def run(host="127.0.0.1", port=8000, worlds=None, character_dir=None):
    load_characters(worlds=worlds, character_dir=character_dir)
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"sint-game РПГ → http://{host}:{port}   (чат: /chat)   {len(CHARACTERS)} персонажей")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstop")
    finally:
        srv.server_close()


if __name__ == "__main__":
    run()
