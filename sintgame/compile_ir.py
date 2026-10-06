#!/usr/bin/env python3
"""compile_ir.py — LLM компилирует ЛОР в БОГАТУЮ IR (машины/время/агенты),
понижает в плоский мир и ПРОВЕРЯЕТ доказательствами (prove) ДО приёмки.

Пайплайн (та самая «лестница»):
    лор → [LLM] → спека-IR → link/тайпчек → compile_game → плоский мир
                                                        → validate → prove
Концовка, ДОКАЗАННО недостижимая, — ошибка компиляции (не «повезло/не повезло»).

generator инъектируется: логика проверяется без LLM.
"""
from .abstract import prove
from .gen import gen_json
from .ir import compile_game, link
from .schema import simulate, validate

IR_SCHEMA = """СПЕКА ИГРЫ (один JSON):
{
 "title":str, "tone":str, "seed":int,
 "entities": {"<id>": {"type":str,"tags":[str],"attrs":{"<name>":number},"desc":str,"voice":str}},
 "holds": [["<holder>","<item>"]],
 "relations": [["<a>","<b>","<type>",number]],
 "flags": {"<name>":0},
 "actions": [{"id":str,"label":str,"pre":[COND],"eff":[EFF],"agent":str?}],
 "triggers": [{"pre":[COND],"eff":[EFF],"once":bool}],
 "machines": {"<id>": {"initial":"<region>","regions":["a","b"],
                        "transitions":[{"from":"a","to":"b","pre":[COND],"eff":[EFF],"once":bool}],
                        "children":{"<cid>":{ ... ,"when":"<parent_region>"}}}},
 "time": {"carrier":"<entity_id>","cooldowns":{"<name>":number},
          "periodic":[{"cd":"<name>","pre":[COND],"eff":[EFF],"once":bool}]},
 "constraints": {"vital":["<id>"],"min_hp":1}
}
COND (И): ["flag",name] ["not",COND] ["gt"|"lt"|"ge"|"le"|"eq","<id>.<attr>"|flag,number]
           ["has",holder,item] ["rel_gt"|"rel_lt",a,b,type,number]
EFF:       ["set",path,val] ["add",path,num] ["flag",name,0|1] ["give"|"take",holder,item]
           ["dmg"|"heal",id,num|{"roll":"1d6","plus":"<id>.<attr>"}] ["rel",a,b,type,num]
           ["say",text] ["end",ending_id]
"""


def ir_prompt(lore):
    return ("Ты — компилятор игровой ЛОГИКИ. Вход: лор. Выход: ОДИН JSON — спека игры.\n"
            "Используй МАШИНЫ для многофазной логики, ВРЕМЯ для периодики/кулдаунов, "
            "AGENTS для чужих акторов. Не возвращай markdown.\n\n"
            + IR_SCHEMA + "\n\nЛОР:\n" + lore)


def _default_generator(prompt):
    return gen_json(prompt)[0]


def compile_ir(lore, rounds=3, generator=None) -> tuple[dict | None, dict]:
    gen = generator or _default_generator
    base = ir_prompt(lore)
    prompt = base
    last = []
    for _ in range(rounds):
        spec = gen(prompt)
        if not isinstance(spec, dict):
            last = ["generator returned no IR spec"]
            prompt = base + "\n\nИСПРАВЬ: верни JSON-спеку."
            continue
        errs = link(spec)
        if errs:
            last = errs
            prompt = base + "\n\nИСПРАВЬ ошибки линковки:\n" + "\n".join(errs)
            continue
        world = compile_game(spec)
        errs = validate(world)
        if errs:
            last = errs
            prompt = base + "\n\nИСПРАВЬ ошибки мира:\n" + "\n".join(errs)
            continue
        pr = prove(world)
        if pr["proven_unreachable"]:
            last = [f"proven unreachable endings: {pr['proven_unreachable']}"]
            prompt = base + "\n\nСДЕЛАЙ КОНЦОВКИ ДОСТИЖИМЫМИ: " + str(pr["proven_unreachable"])
            continue
        report: dict = {"proof": pr, "sim": simulate(world)}
        if pr["invariant_may_violate"] or pr["dead_end_possible"]:
            report["warnings"] = {"invariant_may_violate": pr["invariant_may_violate"],
                                  "dead_end_possible": pr["dead_end_possible"]}
        return world, report
    return None, {"errors": last}
