#!/usr/bin/env python3
"""compile_world.py — lore.md -> world.json, with an AGENT as the compiler.

The LLM (a sibling opencode agent via SINT_GEN_CMD) fills the schema.
The validator gates the output; invalid worlds are bounced back for repair.
"""
import argparse
import json
import sys

from .gen import gen_json
from .schema import SCHEMA_TEXT, simulate, validate

PROMPT = """Ты — компилятор игрового мира. Вход: лор. Выход: ОДИН JSON-объект (мир) строго по схеме.
Без markdown, без пояснений — только JSON.

{schema}

ТРЕБОВАНИЯ:
- id сущностей — латиница, snake_case; игрок обязан иметь id "player" и attrs hp, hp_max.
- каждое действие: {{"id","label","pre":[COND],"eff":[EFF]}}; pre может быть пустым списком.
- в мире >= 6 действий, >= 2 параллельные линии (например разговорная и силовая).
- каждая концовка = эффект ["end","<ending_id>"] с предшествующим ["say","..."].
- минимум 3 РАЗНЫЕ достижимые концовки; связи персонажей — через relations и эффект ["rel",...].
- триггеры (once=true) для реакций мира: смерть, провал, разоблачение.
- attrs: у акторов hp/hp_max; добавляй релевантные (trust, cold, guilt...).
- у персонажей поле "voice" — КАК они говорят (тон, манера, длина реплик) — для консистентности прозы.
- блок "constraints": {{"vital":[...],"min_hp":1}} — перечисли персонажей, которые НЕ должны
  погибать от произвольных действий игрока (это инвариант для ворот рантайма).
- текст в "say" и "desc" — на русском, в тоне лора.

ЛОР:
{lore}
"""


SANDBOX_PROMPT = """Ты — компилятор ОТКРЫТОГО игрового мира (сэндбокс). Вход: лор. Выход: ОДИН JSON-объект по схеме. Только JSON.

{schema}

ТРЕБОВАНИЯ (сэндбокс, без финала):
- id сущностей — латиница, snake_case; игрок обязан иметь id "player" и attrs hp, hp_max.
- НЕ используй эффект ["end", ...] вообще — у мира НЕТ финала (открытый мир).
- >= 20 действий; многие — рутинные и УСЛОВНЫЕ (торг, вода, сон, ремонт, разведка, работа).
- ресурсы (вода, деньги, усталость, доверие, износ) ГЕЙТЯТ доступность действий через pre.
- триггеры только МЕНЯЮТ состояние (не завершают игру).
- мир должен позволять играть сотни ходов: всегда есть дешёвое доступное действие.
- блок "constraints": {{"vital":[...],"min_hp":1}} — кто не должен погибать.
- текст "say"/"desc"/"voice" — на русском, в тоне лора.

ЛОР:
{lore}
"""


def compile_world(lore, rounds=3, sandbox=False):
    prompt = (SANDBOX_PROMPT if sandbox else PROMPT).format(schema=SCHEMA_TEXT, lore=lore)
    for i in range(rounds):
        world, raw = gen_json(prompt)
        if world is None:
            print(f"[compile] round {i+1}: no JSON in output", file=sys.stderr)
            prompt += "\n\nВАЖНО: ответ должен быть ТОЛЬКО JSON-объектом мира."
            continue
        errs = validate(world)
        if not errs:
            return world, simulate(world)
        print(f"[compile] round {i+1}: {len(errs)} validation error(s)", file=sys.stderr)
        for e in errs[:12]:
            print("   -", e, file=sys.stderr)
        prompt += "\n\nИСПРАВЬ ОШИБКИ ВАЛИДАТОРА и верни мир целиком:\n" + "\n".join(errs)
    return None, None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("lore")
    ap.add_argument("-o", "--out", default="world.json")
    ap.add_argument("--rounds", type=int, default=3)
    a = ap.parse_args()
    lore = open(a.lore).read()
    world, sim = compile_world(lore, a.rounds)
    if not world:
        print("COMPILE FAILED")
        sys.exit(1)
    json.dump(world, open(a.out, "w"), ensure_ascii=False, indent=2)
    print(f"COMPILED -> {a.out}: {world.get('title')}")
    print("SIMULATION:", json.dumps(sim, ensure_ascii=False))
