#!/usr/bin/env python3
"""Generator adapter — puts an AGENT into the generation loop.

SINT_GEN_CMD   command that reads a prompt as its last arg and writes a completion
               to stdout. Default: `opencode run --pure` (a sibling opencode agent).
SINT_GEN_CWD   working dir for that command (default /tmp)
SINT_GEN_TIMEOUT seconds (default 180)
"""
import json
import os
import re
import shlex
import subprocess

DEFAULT_CMD = "opencode run --pure"


def call(prompt, cmd=None, timeout=None, cwd=None):
    cmd = cmd or os.environ.get("SINT_GEN_CMD", DEFAULT_CMD)
    timeout = timeout or int(os.environ.get("SINT_GEN_TIMEOUT", "180"))
    cwd = cwd or os.environ.get("SINT_GEN_CWD", "/tmp")
    args = shlex.split(cmd) + [prompt]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        # нет LLM / нет команды / таймаут -> пустой ответ; вызывающий код деградирует штатно
        return ""
    return (p.stdout or "") + (("\n" + p.stderr) if p.returncode else "")


def extract_json(s):
    if not s:
        return None
    s = re.sub(r"```(?:json)?", "", s).replace("```", "").strip()
    start = s.find("{")
    while start != -1:
        depth, instr, esc = 0, False, False
        for i in range(start, len(s)):
            c = s[i]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    instr = False
            else:
                if c == '"':
                    instr = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(s[start:i + 1])
                        except Exception:
                            break
        start = s.find("{", start + 1)
    return None


def gen_json(prompt, retries=2):
    last = None
    for _ in range(retries + 1):
        raw = call(prompt)
        obj = extract_json(raw)
        if obj is not None:
            return obj, raw
        last = raw
        prompt = prompt + "\n\nВАЖНО: предыдущий ответ не был валидным JSON. Ответь ОДНИМ JSON-объектом, без markdown."
    return None, last


def gen_text(prompt):
    return call(prompt).strip()
