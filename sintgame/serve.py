#!/usr/bin/env python3
"""serve.py — локальный веб-чат с персонажами (аналог character.ai, но на ноуте).

Только стандартная библиотека: http.server + встроенный HTML. Персонажи берутся из
world.json (NPC) и/или каталога карточек. Сессии — в памяти процесса.

  sintgame serve --port 8000
  → http://127.0.0.1:8000
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import chat

SESSIONS = {}
CHARACTERS = {}


def _default_worlds():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ex = os.path.join(root, "examples")
    return [os.path.join(ex, d, "world.json") for d in sorted(os.listdir(ex))
            if os.path.exists(os.path.join(ex, d, "world.json"))]


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


HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>sint-game · чат</title>
<style>
:root{--bg:#1a1b26;--fg:#c0caf5;--dim:#565f89;--acc:#7aa2f7;--bg2:#24283b}
*{box-sizing:border-box}
body{margin:0;height:100vh;display:flex;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
aside{width:260px;border-right:1px solid #2f3549;padding:12px;overflow:auto}
aside h2{font-size:13px;color:var(--dim);text-transform:uppercase;margin:0 0 8px}
.char{padding:8px 10px;border-radius:8px;cursor:pointer;margin-bottom:4px}
.char:hover{background:var(--bg2)} .char.sel{background:var(--acc);color:#1a1b26}
main{flex:1;display:flex;flex-direction:column;min-width:0}
header{padding:10px 16px;border-bottom:1px solid #2f3549}
header b{font-size:16px} header span{color:var(--dim);font-size:13px}
#log{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.msg{max-width:70%;padding:10px 14px;border-radius:12px;white-space:pre-wrap}
.me{align-self:flex-end;background:var(--acc);color:#1a1b26}
.bot{align-self:flex-start;background:var(--bg2)}
form{display:flex;gap:8px;padding:12px 16px;border-top:1px solid #2f3549}
input{flex:1;background:#16161e;color:var(--fg);border:1px solid #2f3549;border-radius:8px;padding:10px 12px;font:inherit}
button{background:var(--acc);color:#1a1b26;border:0;border-radius:8px;padding:10px 18px;font:inherit;cursor:pointer}
.muted{color:var(--dim);font-size:13px}
</style></head><body>
<aside><h2>Персонажи</h2><div id="chars" class="muted">загрузка…</div></aside>
<main>
  <header><b id="cname">—</b> <span id="cmeta"></span></header>
  <div id="log"></div>
  <form id="f"><input id="in" placeholder="Написать…" autocomplete="off" autofocus><button>Отправить</button></form>
</main>
<script>
let CHARS=[], CUR=null, HIST=[], SID="local-"+Math.random().toString(36).slice(2,8);
const $=s=>document.querySelector(s);
async function loadChars(){ CHARS = await (await fetch('/api/characters')).json();
  $('#chars').innerHTML = CHARS.map(c=>`<div class="char" data-id="${c.id}">${c.name||c.id}<div class="muted">${(c.voice||'').slice(0,40)}</div></div>`).join('') || '<div class="muted">нет персонажей</div>';
  document.querySelectorAll('.char').forEach(el=>el.onclick=()=>select(el.dataset.id));
  if(CHARS[0]) select(CHARS[0].id);
}
function select(id){ CUR=CHARS.find(c=>c.id===id); HIST=[]; $('#cname').textContent=CUR.name||CUR.id; $('#cmeta').textContent=CUR.persona||''; $('#log').innerHTML=''; document.querySelectorAll('.char').forEach(e=>e.classList.toggle('sel',e.dataset.id===id)); }
function add(cls,txt){ const d=document.createElement('div'); d.className='msg '+cls; d.textContent=txt; $('#log').appendChild(d); $('#log').scrollTop=$('#log').scrollHeight; }
$('#f').onsubmit=async e=>{ e.preventDefault(); const m=$('#in').value.trim(); if(!m||!CUR) return; add('me',m); $('#in').value='';
  const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({character:CUR.id,message:m,session:SID})});
  const j=await r.json(); add('bot', j.reply); };
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

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(HTML.encode(), "text/html; charset=utf-8")
        elif self.path == "/api/characters":
            self._json(list(CHARACTERS.values()))
        elif self.path == "/api/health":
            self._json({"ok": True, "characters": len(CHARACTERS)})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/api/chat":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json({"error": "bad json"}, 400)
        cid = body.get("character")
        char = CHARACTERS.get(cid) or next(iter(CHARACTERS.values()), None)
        if not char:
            return self._json({"error": "no characters"}, 400)
        msg = str(body.get("message", ""))[:4000]
        st = SESSIONS.setdefault(body.get("session", "default"), {"history": [], "facts": []})
        text = chat.reply(char, msg, st["history"], st["facts"])
        name = char.get("name", "Персонаж")
        st["history"].append(f"Пользователь: {msg}")
        st["history"].append(f"{name}: {text}")
        st["history"] = st["history"][-40:]
        if len(msg) > 15:
            st["facts"].append(msg.strip())
        st["facts"] = st["facts"][-20:]
        self._json({"reply": text, "character": name})

    def log_message(self, format, *args):
        pass


def run(host="127.0.0.1", port=8000, worlds=None, character_dir=None):
    load_characters(worlds=worlds, character_dir=character_dir)
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"sint-game chat → http://{host}:{port}  ({len(CHARACTERS)} персонажей)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstop")
    finally:
        srv.server_close()


if __name__ == "__main__":
    run()
