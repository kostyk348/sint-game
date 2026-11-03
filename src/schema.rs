//! Порт `schema.py`: валидатор мира + stability + simulate.
//!
//! `validate` реально отклоняет некорректные миры (битые сущности, действия
//! без эффектов, нет доступного действия на старте, петли триггеров).
//! `simulate` — случайные прогоны с бит-точным CPython RNG: концовки, тупики,
//! средняя длина партии совпадают с Python при тех же seeds.

use serde_json::{json, Value};

use crate::world::World;

const GUARD_CASCADE: &str = "unstable: петля триггеров — каскад упирается в guard";

/// JSON-рендер значения для текстов ошибок (в Python это repr, в порту — JSON).
fn jstr<T: serde::Serialize>(v: &T) -> String {
    serde_json::to_string(v).unwrap_or_default()
}

fn check_cond(
    c: &Value,
    ents: &std::collections::BTreeSet<String>,
    errs: &mut Vec<String>,
    ctx: &str,
) {
    let Some(arr) = c.as_array() else {
        errs.push(format!("{ctx}: bad COND {}", jstr(c)));
        return;
    };
    if arr.is_empty() {
        errs.push(format!("{ctx}: bad COND {}", jstr(c)));
        return;
    }
    let c = arr;
    let Some(op) = c[0].as_str() else {
        errs.push(format!("{ctx}: bad COND {}", jstr(c)));
        return;
    };
    match op {
        "flag" => {}
        "not" => {
            if let Some(inner) = c.get(1) {
                check_cond(inner, ents, errs, ctx);
            }
        }
        "gt" | "lt" | "ge" | "le" | "eq" => {
            if let Some(Value::String(p)) = c.get(1) {
                if p.contains('.') {
                    let id = p.split('.').next().unwrap_or("");
                    if !ents.contains(id) {
                        errs.push(format!("{ctx}: unknown entity '{id}' in {}", jstr(c)));
                    }
                }
            }
        }
        "has" | "rel_gt" | "rel_lt" => {
            for idx in [1usize, 2] {
                if let Some(Value::String(id)) = c.get(idx) {
                    if !ents.contains(id) {
                        errs.push(format!("{ctx}: unknown entity '{id}' in {}", jstr(c)));
                    }
                }
            }
        }
        other => errs.push(format!("{ctx}: unknown COND op '{other}'")),
    }
}

fn check_eff(
    x: &Value,
    ents: &std::collections::BTreeSet<String>,
    errs: &mut Vec<String>,
    ctx: &str,
) {
    let Some(arr) = x.as_array() else {
        errs.push(format!("{ctx}: bad EFF {}", jstr(x)));
        return;
    };
    if arr.is_empty() {
        errs.push(format!("{ctx}: bad EFF {}", jstr(x)));
        return;
    }
    let x = arr;
    let Some(op) = x[0].as_str() else {
        errs.push(format!("{ctx}: bad EFF {}", jstr(x)));
        return;
    };
    match op {
        "set" | "add" => {
            if let Some(Value::String(p)) = x.get(1) {
                if p.contains('.') {
                    let id = p.split('.').next().unwrap_or("");
                    if !ents.contains(id) {
                        errs.push(format!("{ctx}: unknown entity '{id}' in {}", jstr(x)));
                    }
                }
            }
        }
        "flag" => {}
        "give" | "take" => {
            if let Some(Value::String(id)) = x.get(1) {
                if !ents.contains(id) {
                    errs.push(format!("{ctx}: unknown entity '{id}' in {}", jstr(x)));
                }
            }
            if let Some(Value::String(item)) = x.get(2) {
                if !ents.contains(item) {
                    errs.push(format!("{ctx}: unknown item '{item}' in {}", jstr(x)));
                }
            }
        }
        "dmg" | "heal" => {
            if let Some(Value::String(id)) = x.get(1) {
                if !ents.contains(id) {
                    errs.push(format!("{ctx}: unknown entity '{id}' in {}", jstr(x)));
                }
            }
        }
        "rel" => {
            for idx in [1usize, 2] {
                if let Some(Value::String(id)) = x.get(idx) {
                    if !ents.contains(id) {
                        errs.push(format!("{ctx}: unknown entity '{id}' in {}", jstr(x)));
                    }
                }
            }
        }
        "say" | "end" => {}
        other => errs.push(format!("{ctx}: unknown EFF op '{other}'")),
    }
}

/// Сколько прогонов упираются в guard каскада триггеров (петля триггеров).
pub fn stability(data: &Value, trials: usize, depth: usize, seed0: i64) -> usize {
    let mut unstable = 0;
    for t in 0..trials {
        let seed = seed0 + t as i64;
        let mut w = World::new(data.clone(), Some(seed), false);
        let mut rng = crate::rng::PyRandom::new(seed);
        for _ in 0..depth {
            if w.ended.is_some() {
                break;
            }
            let acts = w.available(None);
            if acts.is_empty() {
                break;
            }
            let pick = rng.below_for_choice(acts.len());
            let aid = acts[pick]
                .get("id")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            w.act(&aid);
            if w.hit_guard {
                unstable += 1;
                break;
            }
        }
    }
    unstable
}

/// Валидатор мира. Пустой список = мир играбелен.
pub fn validate(data: &Value) -> Vec<String> {
    let mut errs = Vec::new();
    let Some(obj) = data.as_object() else {
        return vec!["root is not an object".to_string()];
    };
    let ents: std::collections::BTreeSet<String> = obj
        .get("entities")
        .and_then(|v| v.as_object())
        .map(|o| o.keys().cloned().collect())
        .unwrap_or_default();
    if !ents.contains("player") {
        errs.push("no entity with id 'player'".to_string());
    }
    if let Some(cons) = obj.get("constraints").and_then(|v| v.as_object()) {
        if let Some(vital) = cons.get("vital").and_then(|v| v.as_array()) {
            for vid in vital {
                if let Value::String(id) = vid {
                    if !ents.contains(id) {
                        errs.push(format!("constraints.vital: unknown entity '{id}'"));
                    }
                }
            }
        }
    }
    let actions_empty = obj
        .get("actions")
        .and_then(|v| v.as_array())
        .map(|a| a.is_empty())
        .unwrap_or(true);
    if actions_empty {
        errs.push("no actions".to_string());
    }
    if let Some(actions) = obj.get("actions").and_then(|v| v.as_array()) {
        for a in actions {
            let id = a.get("id").and_then(|v| v.as_str()).unwrap_or("");
            for k in ["id", "label"] {
                if a.get(k).is_none() {
                    errs.push(format!("action missing '{k}': {}", jstr(a)));
                }
            }
            let eff_missing = a
                .get("eff")
                .and_then(|v| v.as_array())
                .map(|e| e.is_empty())
                .unwrap_or(true);
            if eff_missing {
                errs.push(format!("action {id} has no effects"));
            }
            if let Some(pres) = a.get("pre").and_then(|v| v.as_array()) {
                for c in pres {
                    check_cond(c, &ents, &mut errs, &format!("action {id} pre"));
                }
            }
            if let Some(effs) = a.get("eff").and_then(|v| v.as_array()) {
                for x in effs {
                    check_eff(x, &ents, &mut errs, &format!("action {id} eff"));
                }
            }
        }
    }
    if let Some(triggers) = obj.get("triggers").and_then(|v| v.as_array()) {
        for t in triggers {
            if let Some(pres) = t.get("pre").and_then(|v| v.as_array()) {
                for c in pres {
                    check_cond(c, &ents, &mut errs, "trigger pre");
                }
            }
            if let Some(effs) = t.get("eff").and_then(|v| v.as_array()) {
                for x in effs {
                    check_eff(x, &ents, &mut errs, "trigger eff");
                }
            }
        }
    }
    // на старте должно быть доступно хотя бы одно действие
    let w = World::new(data.clone(), Some(1), false);
    if w.available(None).is_empty() {
        errs.push("no action available at start".to_string());
    }
    // стабильность: петля триггеров — это баг мира, а не дизайн
    if errs.is_empty() {
        let u = stability(data, 20, 60, 10);
        if u > 0 {
            errs.push(format!("{GUARD_CASCADE} в {u} прогонах"));
        }
    }
    errs
}

/// Случайные прогоны: концовки, тупики, нестабильность, средняя длина партии.
pub fn simulate(data: &Value, trials: usize, depth: usize, seed0: i64) -> Value {
    let mut reached: std::collections::BTreeMap<String, u64> = Default::default();
    let mut dead_ends = 0u64;
    let mut unstable = 0u64;
    let mut no_end = 0u64;
    let mut lengths: Vec<u64> = Vec::new();
    for t in 0..trials {
        let seed = seed0 + t as i64;
        let mut w = World::new(data.clone(), Some(seed), false);
        let mut rng = crate::rng::PyRandom::new(seed);
        let mut step = 0usize;
        for step_i in 0..depth {
            step = step_i;
            if w.ended.is_some() {
                break;
            }
            let acts = w.available(None);
            if acts.is_empty() {
                dead_ends += 1;
                break;
            }
            let pick = rng.below_for_choice(acts.len());
            let aid = acts[pick]
                .get("id")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            w.act(&aid);
            if w.hit_guard {
                unstable += 1;
                break;
            }
        }
        if let Some(e) = w.ended.clone() {
            *reached.entry(e).or_insert(0) += 1;
            lengths.push(step as u64 + 1);
        } else {
            no_end += 1;
        }
    }
    let avg = if lengths.is_empty() {
        json!(0)
    } else {
        let sum: f64 = lengths.iter().sum::<u64>() as f64;
        json!((sum / lengths.len() as f64 * 10.0).round() / 10.0)
    };
    json!({
        "endings_reached": reached,
        "dead_ends": dead_ends,
        "unstable": unstable,
        "no_ending": no_end,
        "trials": trials,
        "avg_turns": avg,
    })
}
