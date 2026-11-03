//! Порт `ir.py`: богатая спека → плоский мир ядра.
//!
//! Автор (или LLM) описывает логику богато — машины состояний, время/кулдауны,
//! агенты, — а компилятор ПОНИЖАЕТ её в простую детерминированную модель ядра:
//!   машина  -> по флагу на регион `m_<id>_<region>`; переход = триггер;
//!   время   -> атрибут-кулдаун + скрытое действие `__tick__` + периодический
//!              триггер, сбрасывающий кулдаун;
//!   агенты  -> поле `agent` у действия (ядро фильтрует available(actor)).
//! Анализ (abstract.py) читает уже понижённые переходы, поэтому доказательства
//! работают для машин и времени без переписывания.

use serde_json::{json, Map, Value};

fn deep(v: &Value) -> Value {
    v.clone()
}

fn as_obj(v: Option<&Value>) -> Map<String, Value> {
    v.and_then(|x| x.as_object()).cloned().unwrap_or_default()
}

/// Понижение богатой спеки в плоский world.json для ядра.
pub fn compile_game(spec: &Value) -> Value {
    let spec_ents = as_obj(spec.get("entities"));
    let mut entities = Map::new();
    for (k, v) in &spec_ents {
        entities.insert(k.clone(), deep(v));
    }
    let mut world = json!({
        "schema": 1,
        "title": spec.get("title").and_then(|v| v.as_str()).unwrap_or("ir"),
        "tone": spec.get("tone").and_then(|v| v.as_str()).unwrap_or("neutral"),
        "seed": spec.get("seed").and_then(|v| v.as_i64()).unwrap_or(1),
        "entities": Value::Object(entities),
        "holds": spec.get("holds").cloned().unwrap_or_else(|| json!([])),
        "relations": spec.get("relations").cloned().unwrap_or_else(|| json!([])),
        "flags": spec.get("flags").cloned().unwrap_or_else(|| json!({})),
        "actions": spec.get("actions").cloned().unwrap_or_else(|| json!([])),
        "triggers": spec.get("triggers").cloned().unwrap_or_else(|| json!([])),
    });

    // --- машины состояний (иерархия): регион -> флаг, переход -> триггер ------
    let machines = as_obj(spec.get("machines"));
    if !machines.is_empty() {
        let mut flags = world
            .get("flags")
            .and_then(|v| v.as_object())
            .cloned()
            .unwrap_or_default();
        let mut triggers = world
            .get("triggers")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        for (mid, m) in &machines {
            compile_machine(mid, m, &mut flags, &mut triggers, &[], "m_");
        }
        world["flags"] = Value::Object(flags);
        world["triggers"] = Value::Array(triggers);
    }

    // --- время: кулдауны + периодика ------------------------------------------
    let tm = as_obj(spec.get("time"));
    if !tm.is_empty() {
        let carrier = tm
            .get("carrier")
            .and_then(|v| v.as_str())
            .unwrap_or("player")
            .to_string();
        let cooldowns = as_obj(tm.get("cooldowns"));
        if !cooldowns.is_empty() {
            let ents = world
                .get_mut("entities")
                .and_then(|v| v.as_object_mut())
                .unwrap();
            let e = ents
                .entry(carrier.clone())
                .or_insert_with(|| json!({"type": "actor", "tags": [], "attrs": {}}));
            let attrs = e
                .as_object_mut()
                .unwrap()
                .entry("attrs")
                .or_insert_with(|| json!({}));
            for (cd, period) in &cooldowns {
                attrs
                    .as_object_mut()
                    .unwrap()
                    .insert(format!("cd_{cd}"), period.clone());
            }
            let tick_eff: Vec<Value> = cooldowns
                .keys()
                .map(|cd| json!(["add", format!("{carrier}.cd_{cd}"), -1]))
                .collect();
            world
                .get_mut("actions")
                .and_then(|v| v.as_array_mut())
                .unwrap()
                .push(json!({
                    "id": "__tick__", "label": "time", "pre": [],
                    "eff": tick_eff, "hidden": true
                }));
            if let Some(periodic) = tm.get("periodic").and_then(|v| v.as_array()) {
                for p in periodic {
                    let cd = p.get("cd").and_then(|v| v.as_str()).unwrap_or("");
                    let period = cooldowns.get(cd).cloned().unwrap_or_else(|| json!(0));
                    let mut pre = vec![json!(["le", format!("{carrier}.cd_{cd}"), 0])];
                    if let Some(extra) = p.get("pre").and_then(|v| v.as_array()) {
                        pre.extend(extra.iter().cloned());
                    }
                    let mut eff = vec![json!(["set", format!("{carrier}.cd_{cd}"), period])];
                    if let Some(extra) = p.get("eff").and_then(|v| v.as_array()) {
                        eff.extend(extra.iter().cloned());
                    }
                    world
                        .get_mut("triggers")
                        .and_then(|v| v.as_array_mut())
                        .unwrap()
                        .push(json!({
                            "pre": pre, "eff": eff,
                            "once": p.get("once").and_then(|v| v.as_bool()).unwrap_or(false)
                        }));
                }
            }
        }
    }

    if let Some(c) = spec.get("constraints") {
        world["constraints"] = c.clone();
    }
    world
}

fn machine_flags(mid: &str, m: &Value, prefix: &str, out: &mut Vec<String>) {
    if let Some(regions) = m.get("regions").and_then(|v| v.as_array()) {
        for r in regions {
            if let Some(r) = r.as_str() {
                out.push(format!("{prefix}{mid}_{r}"));
            }
        }
    }
    let children = as_obj(m.get("children"));
    for (cid, cm) in &children {
        machine_flags(cid, cm, &format!("{prefix}{mid}_"), out);
    }
}

fn compile_machine(
    mid: &str,
    m: &Value,
    flags: &mut Map<String, Value>,
    triggers: &mut Vec<Value>,
    guard: &[Value],
    prefix: &str,
) {
    let regions: Vec<&str> = m
        .get("regions")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().filter_map(|x| x.as_str()).collect())
        .unwrap_or_default();
    let initial = m
        .get("initial")
        .and_then(|v| v.as_str())
        .unwrap_or(regions.first().copied().unwrap_or(""));
    for r in &regions {
        flags.insert(
            format!("{prefix}{mid}_{r}"),
            json!(if *r == initial { 1 } else { 0 }),
        );
    }
    if let Some(transitions) = m.get("transitions").and_then(|v| v.as_array()) {
        for t in transitions {
            let from = t.get("from").and_then(|v| v.as_str()).unwrap_or("");
            let to = t.get("to").and_then(|v| v.as_str()).unwrap_or("");
            let mut pre = vec![json!(["flag", format!("{prefix}{mid}_{from}")])];
            pre.extend(guard.iter().cloned());
            if let Some(extra) = t.get("pre").and_then(|v| v.as_array()) {
                pre.extend(extra.iter().cloned());
            }
            let mut eff = vec![
                json!(["flag", format!("{prefix}{mid}_{from}"), 0]),
                json!(["flag", format!("{prefix}{mid}_{to}"), 1]),
            ];
            if let Some(extra) = t.get("eff").and_then(|v| v.as_array()) {
                eff.extend(extra.iter().cloned());
            }
            triggers.push(json!({
                "pre": pre, "eff": eff,
                "once": t.get("once").and_then(|v| v.as_bool()).unwrap_or(false)
            }));
        }
    }
    let children = as_obj(m.get("children"));
    for (cid, cm) in &children {
        let mut g2: Vec<Value> = guard.to_vec();
        if let Some(when) = cm.get("when").and_then(|v| v.as_str()) {
            g2.push(json!(["flag", format!("{prefix}{mid}_{when}")]));
        }
        compile_machine(cid, cm, flags, triggers, &g2, &format!("{prefix}{mid}_"));
    }
}

fn link_machine(mid: &str, m: &Value, errs: &mut Vec<String>) {
    let regions: Vec<&str> = m
        .get("regions")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().filter_map(|x| x.as_str()).collect())
        .unwrap_or_default();
    let init = m
        .get("initial")
        .and_then(|v| v.as_str())
        .unwrap_or(regions.first().copied().unwrap_or(""));
    if !regions.contains(&init) {
        errs.push(format!("machine {mid}: initial '{init}' not in regions"));
    }
    if let Some(transitions) = m.get("transitions").and_then(|v| v.as_array()) {
        for t in transitions {
            let from = t.get("from").and_then(|v| v.as_str()).unwrap_or("");
            let to = t.get("to").and_then(|v| v.as_str()).unwrap_or("");
            if !regions.contains(&from) {
                errs.push(format!("machine {mid}: transition from '{from}' unknown"));
            }
            if !regions.contains(&to) {
                errs.push(format!("machine {mid}: transition to '{to}' unknown"));
            }
        }
    }
    let children = as_obj(m.get("children"));
    for (cid, cm) in &children {
        if let Some(when) = cm.get("when").and_then(|v| v.as_str()) {
            if !regions.contains(&when) {
                errs.push(format!("machine {mid}: child {cid} when '{when}' unknown"));
            }
        }
        link_machine(cid, cm, errs);
    }
}

/// Линковка/тайпчек спеки ДО компиляции: неизвестные сущности и флаги,
/// битые регионы машин.
pub fn link(spec: &Value) -> Vec<String> {
    let mut errs = Vec::new();
    let machines = as_obj(spec.get("machines"));
    for (mid, m) in &machines {
        link_machine(mid, m, &mut errs);
    }
    let mut mflags: Vec<String> = Vec::new();
    for (mid, m) in &machines {
        machine_flags(mid, m, "m_", &mut mflags);
    }
    let declared: std::collections::BTreeSet<String> = spec
        .get("flags")
        .and_then(|v| v.as_object())
        .map(|o| o.keys().cloned().collect())
        .unwrap_or_default();
    let mut produced: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    let ents: std::collections::BTreeSet<String> = spec
        .get("entities")
        .and_then(|v| v.as_object())
        .map(|o| o.keys().cloned().collect())
        .unwrap_or_default();

    let mut items: Vec<Value> = Vec::new();
    if let Some(a) = spec.get("actions").and_then(|v| v.as_array()) {
        items.extend(a.iter().cloned());
    }
    if let Some(t) = spec.get("triggers").and_then(|v| v.as_array()) {
        items.extend(t.iter().cloned());
    }
    for a in &items {
        if let Some(effs) = a.get("eff").and_then(|v| v.as_array()) {
            for x in effs {
                let op = x.get(0).and_then(|v| v.as_str()).unwrap_or("");
                if op == "flag" {
                    if let Some(n) = x.get(1).and_then(|v| v.as_str()) {
                        produced.insert(n.to_string());
                    }
                }
                if op == "set" {
                    if let Some(Value::String(p)) = x.get(1) {
                        if !p.contains('.') {
                            produced.insert(p.clone());
                        }
                    }
                }
            }
        }
    }

    fn chk_cond(
        c: &Value,
        declared: &std::collections::BTreeSet<String>,
        mflags: &[String],
        produced: &std::collections::BTreeSet<String>,
        ents: &std::collections::BTreeSet<String>,
        errs: &mut Vec<String>,
    ) {
        let Some(c) = c.as_array() else { return };
        if c.is_empty() {
            return;
        }
        let op = c[0].as_str().unwrap_or("");
        match op {
            "flag" => {
                if let Some(n) = c.get(1).and_then(|v| v.as_str()) {
                    let known = declared.contains(n)
                        || mflags.iter().any(|m| m == n)
                        || produced.contains(n);
                    if !known {
                        errs.push(format!("unknown flag: {n}"));
                    }
                }
            }
            "not" => {
                if let Some(inner) = c.get(1) {
                    chk_cond(inner, declared, mflags, produced, ents, errs);
                }
            }
            "gt" | "lt" | "ge" | "le" | "eq" => {
                if let Some(Value::String(p)) = c.get(1) {
                    if p.contains('.') {
                        let ent = p.split('.').next().unwrap_or("");
                        if !ents.contains(ent) {
                            errs.push(format!("unknown entity: {ent}"));
                        }
                    }
                }
            }
            "has" | "rel_gt" | "rel_lt" => {
                for idx in [1usize, 2] {
                    if let Some(Value::String(e)) = c.get(idx) {
                        if !ents.contains(e) {
                            errs.push(format!("unknown entity: {e}"));
                        }
                    }
                }
            }
            _ => {}
        }
    }

    fn chk_eff(x: &Value, ents: &std::collections::BTreeSet<String>, errs: &mut Vec<String>) {
        let Some(x) = x.as_array() else { return };
        if x.is_empty() {
            return;
        }
        let op = x[0].as_str().unwrap_or("");
        match op {
            "set" | "add" => {
                if let Some(Value::String(p)) = x.get(1) {
                    if p.contains('.') {
                        let ent = p.split('.').next().unwrap_or("");
                        if !ents.contains(ent) {
                            errs.push(format!("unknown entity: {ent}"));
                        }
                    }
                }
            }
            "give" | "take" => {
                for idx in [1usize, 2] {
                    if let Some(Value::String(e)) = x.get(idx) {
                        if !ents.contains(e) {
                            errs.push(format!("unknown entity: {e}"));
                        }
                    }
                }
            }
            "dmg" | "heal" => {
                if let Some(Value::String(e)) = x.get(1) {
                    if !ents.contains(e) {
                        errs.push(format!("unknown entity: {e}"));
                    }
                }
            }
            "rel" => {
                for idx in [1usize, 2] {
                    if let Some(Value::String(e)) = x.get(idx) {
                        if !ents.contains(e) {
                            errs.push(format!("unknown entity: {e}"));
                        }
                    }
                }
            }
            _ => {}
        }
    }

    for a in &items {
        if let Some(pres) = a.get("pre").and_then(|v| v.as_array()) {
            for c in pres {
                chk_cond(c, &declared, &mflags, &produced, &ents, &mut errs);
            }
        }
        if let Some(effs) = a.get("eff").and_then(|v| v.as_array()) {
            for x in effs {
                chk_eff(x, &ents, &mut errs);
            }
        }
    }
    errs
}
