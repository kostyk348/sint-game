//! Порт `kernel.py`: детерминированное ядро sint-game.
//!
//! «LLM предлагает — ворота решают»: состояние меняют только эффекты
//! `set/add/flag/give/take/dmg/heal/rel/say/end` при выполненных условиях
//! `flag/not/gt/lt/ge/le/eq/has/rel_gt/rel_lt`. Ноль LLM в рантайме ядра.
//!
//! Семантика — один в один с Python: числовая башня int/float с
//! сохранением типа, `get` по отсутствующему пути → 0, каскад триггеров
//! с guard=100, `state()` в формате Python (включая 625-словный MT19937).

use serde_json::{Map, Number, Value};

use crate::rng::PyRandom;

pub type Store = Map<String, Value>;

#[derive(Debug, Clone)]
pub struct World {
    /// world.json как данные (действия/триггеры читаются оттуда же)
    pub d: Value,
    pub rng: PyRandom,
    pub nominal: bool,
    /// entities: id -> entity (attrs мутируются)
    pub e: Store,
    /// flags: имя -> 0|1|число
    pub flags: Store,
    /// holds: (holder, item)
    pub holds: Vec<(String, String)>,
    /// relations: (from, to, type) -> вес
    pub rel: std::collections::HashMap<(String, String, String), f64>,
    /// индексы сработавших триггеров (для once)
    pub done: std::collections::BTreeSet<usize>,
    /// финальная концовка (["end", id])
    pub ended: Option<String>,
    /// реплики последнего хода
    pub said: Vec<String>,
    /// каскад триггеров упёрся в guard
    pub hit_guard: bool,
    /// ошибка последнего act
    pub last_error: Option<&'static str>,
}

// ------------------------------------------------------- числовая башня
// Python: int op int -> int; любой float -> float. Храним как Number.

fn num_i(n: i64) -> Value {
    Value::Number(Number::from(n))
}

fn as_f64(v: &Value) -> f64 {
    match v {
        Value::Number(n) => n.as_f64().unwrap_or(0.0),
        _ => 0.0,
    }
}

fn as_i64(v: &Value) -> i64 {
    match v {
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i
            } else {
                n.as_f64().unwrap_or(0.0).trunc() as i64
            }
        }
        _ => 0,
    }
}

fn is_float(v: &Value) -> bool {
    matches!(v, Value::Number(n) if n.as_i64().is_none())
}

fn py_add(a: &Value, b: &Value) -> Value {
    if is_float(a) || is_float(b) {
        Value::Number(Number::from_f64(as_f64(a) + as_f64(b)).unwrap())
    } else {
        num_i(as_i64(a).wrapping_add(as_i64(b)))
    }
}

fn py_sub(a: &Value, b: &Value) -> Value {
    if is_float(a) || is_float(b) {
        Value::Number(Number::from_f64(as_f64(a) - as_f64(b)).unwrap())
    } else {
        num_i(as_i64(a).wrapping_sub(as_i64(b)))
    }
}

/// Python-сравнение чисел (int/float смешанно).
fn py_num_cmp(a: &Value, b: &Value) -> std::cmp::Ordering {
    as_f64(a)
        .partial_cmp(&as_f64(b))
        .unwrap_or(std::cmp::Ordering::Equal)
}

fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().map(|f| f != 0.0).unwrap_or(false),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

/// Python-стиль: целые веса rel сериализуются как int (0, не 0.0).
fn rel_val(w: f64) -> Value {
    if w.fract() == 0.0 && w.abs() < 9.0e15 {
        num_i(w as i64)
    } else {
        Value::Number(Number::from_f64(w).unwrap())
    }
}

fn json_entity() -> Value {
    serde_json::json!({"type": "actor", "tags": [], "attrs": {}})
}

fn as_i64_trunc(v: &Value) -> i64 {
    as_i64(v)
}

impl World {
    pub fn new(data: Value, seed: Option<i64>, nominal: bool) -> World {
        let seed = seed.unwrap_or_else(|| data.get("seed").and_then(|s| s.as_i64()).unwrap_or(0));
        let mut e = Store::new();
        if let Some(ents) = data.get("entities").and_then(|v| v.as_object()) {
            for (k, v) in ents {
                e.insert(k.clone(), v.clone());
            }
        }
        let mut flags = Store::new();
        if let Some(f) = data.get("flags").and_then(|v| v.as_object()) {
            for (k, v) in f {
                flags.insert(k.clone(), v.clone());
            }
        }
        let holds = data
            .get("holds")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|h| {
                        let a = h.get(0)?.as_str()?.to_string();
                        let b = h.get(1)?.as_str()?.to_string();
                        Some((a, b))
                    })
                    .collect()
            })
            .unwrap_or_default();
        let mut rel = std::collections::HashMap::new();
        if let Some(arr) = data.get("relations").and_then(|v| v.as_array()) {
            for r in arr {
                let (a, b, t) = match (r.get(0), r.get(1), r.get(2)) {
                    (Some(Value::String(a)), Some(Value::String(b)), Some(Value::String(t))) => {
                        (a.clone(), b.clone(), t.clone())
                    }
                    _ => continue,
                };
                let w = r.get(3).and_then(|v| v.as_f64()).unwrap_or(0.0);
                rel.insert((a, b, t), w);
            }
        }
        World {
            d: data,
            rng: PyRandom::new(seed),
            nominal,
            e,
            flags,
            holds,
            rel,
            done: std::collections::BTreeSet::new(),
            ended: None,
            said: Vec::new(),
            hit_guard: false,
            last_error: None,
        }
    }

    /// `get("ent.attr")` -> атрибут; `get("flag")` -> флаг; отсутствует -> 0.
    pub fn get(&self, path: &str) -> Value {
        if let Some((ent, att)) = path.split_once('.') {
            self.e
                .get(ent)
                .and_then(|e| e.get("attrs"))
                .and_then(|a| a.get(att))
                .and_then(|v| v.as_number().cloned())
                .map(Value::Number)
                .unwrap_or_else(|| num_i(0))
        } else {
            self.flags.get(path).cloned().unwrap_or_else(|| num_i(0))
        }
    }

    pub fn set(&mut self, path: &str, val: Value) {
        if let Some((ent, att)) = path.split_once('.') {
            let e = self.e.entry(ent.to_string()).or_insert_with(json_entity);
            let attrs = e
                .as_object_mut()
                .unwrap()
                .entry("attrs")
                .or_insert_with(|| Value::Object(Map::new()));
            attrs.as_object_mut().unwrap().insert(att.to_string(), val);
        } else {
            self.flags.insert(path.to_string(), val);
        }
    }

    /// Условие COND: ["flag",name] ["not",COND] ["gt"|...,path,num]
    /// ["has",holder,item] ["rel_gt"|"rel_lt",from,to,type,num].
    pub fn cond(&self, c: &[Value]) -> bool {
        let Some(op) = c.first().and_then(|v| v.as_str()) else {
            return false;
        };
        match op {
            "flag" => c
                .get(1)
                .and_then(|v| v.as_str())
                .map(|n| truthy(&self.get(n)))
                .unwrap_or(false),
            "not" => c
                .get(1)
                .and_then(|v| v.as_array())
                .map(|inner| !self.cond(inner))
                .unwrap_or(false),
            "gt" | "lt" | "ge" | "le" | "eq" => {
                let (Some(path), Some(rhs)) = (c.get(1), c.get(2)) else {
                    return false;
                };
                let l = self.get(path.as_str().unwrap_or(""));
                match op {
                    "gt" => py_num_cmp(&l, rhs) == std::cmp::Ordering::Greater,
                    "lt" => py_num_cmp(&l, rhs) == std::cmp::Ordering::Less,
                    "ge" => py_num_cmp(&l, rhs) != std::cmp::Ordering::Less,
                    "le" => py_num_cmp(&l, rhs) != std::cmp::Ordering::Greater,
                    _ => match (l.as_number(), rhs.as_number()) {
                        (Some(a), Some(b)) => {
                            if is_float(&Value::Number(a.clone()))
                                || is_float(&Value::Number(b.clone()))
                            {
                                as_f64(&Value::Number(a.clone()))
                                    == as_f64(&Value::Number(b.clone()))
                            } else {
                                as_i64(&Value::Number(a.clone()))
                                    == as_i64(&Value::Number(b.clone()))
                            }
                        }
                        _ => l == *rhs,
                    },
                }
            }
            "has" => {
                let (Some(h), Some(i)) = (
                    c.get(1).and_then(|v| v.as_str()),
                    c.get(2).and_then(|v| v.as_str()),
                ) else {
                    return false;
                };
                self.holds.iter().any(|(a, b)| a == h && b == i)
            }
            "rel_gt" | "rel_lt" => {
                let (Some(a), Some(b), Some(t), Some(w)) = (
                    c.get(1).and_then(|v| v.as_str()),
                    c.get(2).and_then(|v| v.as_str()),
                    c.get(3).and_then(|v| v.as_str()),
                    c.get(4).and_then(|v| v.as_f64()),
                ) else {
                    return false;
                };
                let v = self
                    .rel
                    .get(&(a.to_string(), b.to_string(), t.to_string()))
                    .copied()
                    .unwrap_or(0.0);
                if op == "rel_gt" {
                    v > w
                } else {
                    v < w
                }
            }
            _ => false,
        }
    }

    pub fn conds(&self, cs: &[Value]) -> bool {
        cs.iter()
            .all(|c| c.as_array().map(|c| self.cond(c)).unwrap_or(false))
    }

    fn conds_opt(&self, cs: Option<&Vec<Value>>) -> bool {
        match cs {
            Some(cs) => self.conds(cs),
            None => true,
        }
    }

    /// Бросок "NdM" (+ plus/minus от атрибута); в nominal-режиме — номинал.
    pub fn roll(&mut self, expr: &Value) -> Value {
        match expr {
            Value::Number(_) => expr.clone(),
            Value::Object(m) => {
                let mut v: i64 = 0;
                let roll_expr = m
                    .get("roll")
                    .map(|r| match r {
                        Value::Number(_) => r.to_string(),
                        Value::String(s) => s.clone(),
                        other => other.to_string(),
                    })
                    .unwrap_or_else(|| "0d0".to_string());
                if let Some((n_str, d_str)) = roll_expr.split_once('d') {
                    let n: i64 = n_str.trim().parse().unwrap_or(0);
                    let dz: i64 = d_str.trim().parse().unwrap_or(0);
                    if self.nominal {
                        // Python: int(n * (dz + 1) / 2 + 0.5)
                        v = ((n as f64) * ((dz + 1) as f64) / 2.0 + 0.5).trunc() as i64;
                    } else {
                        let mut sum: i64 = 0;
                        for _ in 0..n.max(0) {
                            sum += self.rng.randint(1, dz);
                        }
                        v = sum;
                    }
                }
                if let Some(p) = m.get("plus").and_then(|v| v.as_str()) {
                    v += as_i64_trunc(&self.get(p));
                }
                if let Some(p) = m.get("minus").and_then(|v| v.as_str()) {
                    v -= as_i64_trunc(&self.get(p));
                }
                num_i(v)
            }
            _ => num_i(0),
        }
    }

    /// Эффект EFF.
    pub fn eff(&mut self, x: &[Value]) {
        let Some(op) = x.first().and_then(|v| v.as_str()) else {
            return;
        };
        match op {
            "set" => {
                if let (Some(p), Some(v)) = (x.get(1).and_then(|v| v.as_str()), x.get(2)) {
                    self.set(p, v.clone());
                }
            }
            "add" => {
                if let (Some(p), Some(v)) = (x.get(1).and_then(|v| v.as_str()), x.get(2)) {
                    let cur = self.get(p);
                    self.set(p, py_add(&cur, v));
                }
            }
            "flag" => {
                if let (Some(n), Some(v)) = (x.get(1).and_then(|v| v.as_str()), x.get(2)) {
                    self.flags.insert(n.to_string(), v.clone());
                }
            }
            "give" => {
                if let (Some(h), Some(i)) = (
                    x.get(1).and_then(|v| v.as_str()),
                    x.get(2).and_then(|v| v.as_str()),
                ) {
                    let pair = (h.to_string(), i.to_string());
                    if !self.holds.contains(&pair) {
                        self.holds.push(pair);
                    }
                }
            }
            "take" => {
                if let (Some(h), Some(i)) = (
                    x.get(1).and_then(|v| v.as_str()),
                    x.get(2).and_then(|v| v.as_str()),
                ) {
                    self.holds.retain(|(a, b)| !(a == h && b == i));
                }
            }
            "dmg" | "heal" => {
                if let (Some(id), Some(r)) = (x.get(1).and_then(|v| v.as_str()), x.get(2)) {
                    let path = format!("{id}.hp");
                    let cur = self.get(&path);
                    let delta = self.roll(r);
                    self.set(
                        &path,
                        if op == "dmg" {
                            py_sub(&cur, &delta)
                        } else {
                            py_add(&cur, &delta)
                        },
                    );
                }
            }
            "rel" => {
                if let (Some(a), Some(b), Some(t), Some(w)) = (
                    x.get(1).and_then(|v| v.as_str()),
                    x.get(2).and_then(|v| v.as_str()),
                    x.get(3).and_then(|v| v.as_str()),
                    x.get(4).and_then(|v| v.as_f64()),
                ) {
                    let k = (a.to_string(), b.to_string(), t.to_string());
                    let cur = self.rel.get(&k).copied().unwrap_or(0.0);
                    self.rel.insert(k, cur + w);
                }
            }
            "say" => {
                if let Some(t) = x.get(1).and_then(|v| v.as_str()) {
                    self.said.push(t.to_string());
                }
            }
            "end" => {
                if let Some(e) = x.get(1).and_then(|v| v.as_str()) {
                    self.ended = Some(e.to_string());
                }
            }
            _ => {}
        }
    }

    /// Каскад триггеров: пока что-то меняется, guard < 100.
    pub fn fire(&mut self) {
        let mut changed = true;
        let mut guard = 0u32;
        while changed && self.ended.is_none() && guard < 100 {
            changed = false;
            guard += 1;
            let triggers: Vec<Value> = self
                .d
                .get("triggers")
                .and_then(|v| v.as_array())
                .cloned()
                .unwrap_or_default();
            for (i, t) in triggers.iter().enumerate() {
                if t.get("once").and_then(|v| v.as_bool()).unwrap_or(false)
                    && self.done.contains(&i)
                {
                    continue;
                }
                let pre = t.get("pre").and_then(|v| v.as_array());
                if self.conds_opt(pre) {
                    self.done.insert(i);
                    if let Some(effs) = t.get("eff").and_then(|v| v.as_array()) {
                        for x in effs {
                            if let Some(x) = x.as_array() {
                                self.eff(x);
                            }
                        }
                    }
                    changed = true;
                }
            }
        }
        if guard >= 100 {
            self.hit_guard = true;
        }
    }

    fn actions(&self) -> &[Value] {
        match self.d.get("actions").and_then(|v| v.as_array()) {
            Some(a) => a,
            None => &[],
        }
    }

    fn action_by_id(&self, aid: &str) -> Option<&Value> {
        self.actions()
            .iter()
            .find(|a| a.get("id").and_then(|v| v.as_str()) == Some(aid))
    }

    /// Доступные действия (hidden скрыты; agent-фильтр по актору).
    pub fn available(&self, actor: Option<&str>) -> Vec<Value> {
        self.actions()
            .iter()
            .filter(|a| {
                if a.get("hidden").and_then(|v| v.as_bool()).unwrap_or(false) {
                    return false;
                }
                if let Some(actor) = actor {
                    let agent = a.get("agent").and_then(|v| v.as_str());
                    if agent.is_some() && agent != Some(actor) {
                        return false;
                    }
                }
                self.conds_opt(a.get("pre").and_then(|v| v.as_array()))
            })
            .cloned()
            .collect()
    }

    /// Время: продвинуть кулдауны (__tick__) и дать сработать периодике.
    pub fn tick(&mut self) -> &[String] {
        self.said.clear();
        if let Some(a) = self.action_by_id("__tick__") {
            let effs: Vec<Value> = a
                .get("eff")
                .and_then(|v| v.as_array())
                .cloned()
                .unwrap_or_default();
            for x in effs {
                if let Some(x) = x.as_array() {
                    self.eff(x);
                }
            }
        }
        self.fire();
        &self.said
    }

    pub fn can(&self, aid: &str) -> bool {
        self.action_by_id(aid)
            .map(|a| self.conds_opt(a.get("pre").and_then(|v| v.as_array())))
            .unwrap_or(false)
    }

    /// Исполнить действие; при ложной предусловии — last_error ("unavailable").
    pub fn act(&mut self, aid: &str) -> &[String] {
        self.said.clear();
        self.last_error = None;
        let Some(a) = self.action_by_id(aid) else {
            self.last_error = Some("no such action");
            return &self.said;
        };
        let ok = self.conds_opt(a.get("pre").and_then(|v| v.as_array()));
        if !ok {
            self.last_error = Some("unavailable");
            return &self.said;
        }
        let effs: Vec<Value> = a
            .get("eff")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        for x in effs {
            if let Some(x) = x.as_array() {
                self.eff(x);
            }
        }
        self.fire();
        &self.said
    }

    fn attrs_map(&self) -> Map<String, Value> {
        let mut attrs = Map::new();
        for (id, e) in &self.e {
            let mut a = Map::new();
            if let Some(am) = e.get("attrs").and_then(|v| v.as_object()) {
                for (k, v) in am {
                    a.insert(k.clone(), v.clone());
                }
            }
            attrs.insert(id.clone(), Value::Object(a));
        }
        attrs
    }

    fn holds_sorted(&self) -> Vec<Value> {
        let mut holds: Vec<(String, String)> = self.holds.clone();
        holds.sort();
        holds
            .into_iter()
            .map(|(h, i)| serde_json::json!([h, i]))
            .collect()
    }

    /// Полное сериализуемое состояние ВКЛЮЧАЯ rng (формат Python).
    pub fn state(&self) -> Value {
        let mut rel = Map::new();
        for ((a, b, t), w) in &self.rel {
            rel.insert(format!("{a}|{b}|{t}"), rel_val(*w));
        }
        let (ver, internal, gauss) = self.rng.export_state();
        serde_json::json!({
            "flags": Value::Object(self.flags.clone()),
            "attrs": Value::Object(self.attrs_map()),
            "holds": self.holds_sorted(),
            "rel": Value::Object(rel),
            "done": self.done.iter().collect::<Vec<_>>(),
            "ended": self.ended,
            "rng": {
                "version": ver,
                "internal": internal,
                "gauss": gauss,
            }
        })
    }

    /// Восстановление из state() (или Python-сейва той же формы).
    pub fn restore(&mut self, s: &Value) {
        if let Some(f) = s.get("flags").and_then(|v| v.as_object()) {
            self.flags = f.clone();
        }
        if let Some(attrs) = s.get("attrs").and_then(|v| v.as_object()) {
            for (id, am) in attrs {
                let e = self.e.entry(id.clone()).or_insert_with(json_entity);
                e.as_object_mut()
                    .unwrap()
                    .entry("attrs")
                    .or_insert_with(|| Value::Object(Map::new()))
                    .as_object_mut()
                    .unwrap()
                    .extend(am.as_object().cloned().unwrap_or_default());
            }
        }
        if let Some(arr) = s.get("holds").and_then(|v| v.as_array()) {
            self.holds = arr
                .iter()
                .filter_map(|h| {
                    Some((
                        h.get(0)?.as_str()?.to_string(),
                        h.get(1)?.as_str()?.to_string(),
                    ))
                })
                .collect();
        }
        if let Some(rel) = s.get("rel").and_then(|v| v.as_object()) {
            self.rel.clear();
            for (k, w) in rel {
                let parts: Vec<&str> = k.split('|').collect();
                if parts.len() == 3 {
                    self.rel.insert(
                        (
                            parts[0].to_string(),
                            parts[1].to_string(),
                            parts[2].to_string(),
                        ),
                        w.as_f64().unwrap_or(0.0),
                    );
                }
            }
        }
        if let Some(done) = s.get("done").and_then(|v| v.as_array()) {
            self.done = done
                .iter()
                .filter_map(|v| v.as_u64().map(|i| i as usize))
                .collect();
        }
        self.ended = s.get("ended").and_then(|v| v.as_str()).map(String::from);
        if let Some(rng) = s.get("rng") {
            let ver = rng.get("version").and_then(|v| v.as_u64()).unwrap_or(3);
            let internal: Vec<u32> = rng
                .get("internal")
                .and_then(|v| v.as_array())
                .map(|a| {
                    a.iter()
                        .filter_map(|x| x.as_u64().map(|i| i as u32))
                        .collect()
                })
                .unwrap_or_default();
            let gauss = match rng.get("gauss") {
                Some(Value::Number(n)) => n.as_f64(),
                _ => None,
            };
            self.rng.import_state(ver, &internal, gauss);
        }
    }

    /// Лёгкий снимок (без rng/done) — для diff.
    pub fn snapshot(&self) -> Value {
        let mut rel = Map::new();
        for ((a, b, t), w) in &self.rel {
            rel.insert(format!("{a}>{b}:{t}"), rel_val(*w));
        }
        serde_json::json!({
            "flags": Value::Object(self.flags.clone()),
            "attrs": Value::Object(self.attrs_map()),
            "holds": self.holds_sorted(),
            "rel": Value::Object(rel),
        })
    }

    /// Строка статуса игрока (для CLI/прозы).
    pub fn status(&self) -> String {
        let mut parts = Vec::new();
        if let Some(p) = self
            .e
            .get("player")
            .and_then(|e| e.get("attrs"))
            .and_then(|v| v.as_object())
        {
            for (k, v) in p {
                parts.push(format!("{k}={v}"));
            }
        }
        let fl: Vec<String> = self
            .flags
            .iter()
            .filter(|(_, v)| truthy(v))
            .map(|(k, _)| k.clone())
            .collect();
        let mut out = parts.join(" ");
        if !fl.is_empty() {
            out.push_str(&format!(" | flags=[{}]", fl.join(",")));
        }
        out
    }
}

/// diff(snapshot, snapshot) — человекочитаемые изменения состояния.
pub fn diff(before: &Value, after: &Value) -> Vec<String> {
    let mut out = Vec::new();
    let empty = Map::new();
    let b_attrs = before
        .get("attrs")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let a_attrs = after
        .get("attrs")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    for (k, av) in a_attrs {
        let b = b_attrs.get(k).and_then(|v| v.as_object()).unwrap_or(&empty);
        let am = av.as_object().unwrap_or(&empty);
        for (a2, v) in am {
            if b.get(a2) != Some(v) {
                out.push(format!(
                    "{k}.{a2}: {} -> {}",
                    b.get(a2)
                        .map(|x| x.to_string())
                        .unwrap_or_else(|| "None".into()),
                    v
                ));
            }
        }
    }
    let b_flags = before
        .get("flags")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let a_flags = after
        .get("flags")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    for (k, v) in a_flags {
        if b_flags.get(k) != Some(v) {
            out.push(format!(
                "flag {k}: {} -> {}",
                b_flags
                    .get(k)
                    .map(|x| x.to_string())
                    .unwrap_or_else(|| "None".into()),
                v
            ));
        }
    }
    let as_set = |v: &Value| -> std::collections::BTreeSet<(String, String)> {
        v.get("holds")
            .and_then(|h| h.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|x| {
                        Some((
                            x.get(0)?.as_str()?.to_string(),
                            x.get(1)?.as_str()?.to_string(),
                        ))
                    })
                    .collect()
            })
            .unwrap_or_default()
    };
    let (bh, ah) = (as_set(before), as_set(after));
    for (h, it) in ah.difference(&bh) {
        out.push(format!("+ {it} -> {h}"));
    }
    for (h, it) in bh.difference(&ah) {
        out.push(format!("- {it} from {h}"));
    }
    let b_rel = before
        .get("rel")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    let a_rel = after
        .get("rel")
        .and_then(|v| v.as_object())
        .unwrap_or(&empty);
    for (k, v) in a_rel {
        if b_rel.get(k) != Some(v) {
            out.push(format!(
                "rel {k}: {} -> {}",
                b_rel
                    .get(k)
                    .map(|x| x.to_string())
                    .unwrap_or_else(|| "None".into()),
                v
            ));
        }
    }
    out
}
