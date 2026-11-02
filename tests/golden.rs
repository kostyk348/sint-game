//! Golden-тесты: Rust-ядро sint-game обязано побитово воспроизводить
//! оригинальный Python (kernel/ir/schema) на корпусе example-миров.

use serde_json::Value;
use sintgame::ir;
use sintgame::schema::{simulate, validate};
use sintgame::world::World;

mod golden_cases;
use golden_cases::WORLDS;

fn parse(s: &str) -> Value {
    serde_json::from_str(s).expect("golden JSON должен парситься")
}

fn canonical(v: &Value) -> String {
    serde_json::to_string(v).expect("сериализация")
}

/// Порт scripted_trace из scripts/sintgame_golden.py:
/// всегда первый available; snapshot/said/status/avail на каждом шаге;
/// полное состояние (с rng) на save_at и в конце.
fn scripted_trace(world: &Value, seed: i64, steps: usize, save_at: usize) -> (Value, Value) {
    let mut w = World::new(world.clone(), Some(seed), false);
    let mut trace: Vec<Value> = Vec::new();
    let mut saved: Option<Value> = None;
    for i in 0..steps {
        if w.ended.is_some() {
            break;
        }
        let acts = w.available(None);
        if acts.is_empty() {
            trace.push(serde_json::json!({"t": i, "dead": true}));
            break;
        }
        let aid = acts[0]
            .get("id")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let said = w.act(&aid).to_vec();
        let mut entry = serde_json::json!({
            "t": i,
            "act": aid,
            "said": said,
            "ended": w.ended,
            "snap": canonical(&w.snapshot()),
            "avail": w.available(None).iter()
                .map(|a| a.get("id").cloned().unwrap_or(Value::Null))
                .collect::<Vec<_>>(),
        });
        if i == save_at {
            let st = w.state();
            entry["saved_state"] = Value::String(canonical(&st));
            saved = Some(st);
        }
        trace.push(entry);
    }
    let mut out = serde_json::json!({ "trace": trace, "final_state": canonical(&w.state()) });
    if let Some(saved) = saved {
        let mut w2 = World::new(world.clone(), Some(seed), false);
        w2.restore(&saved);
        out["restored_state"] = Value::String(canonical(&w2.state()));
    }
    (out, w.state())
}

#[test]
fn golden_examples_match_python() {
    for case in WORLDS {
        let world: Value = serde_json::from_str(case.world).expect("world.json");
        let name = case.name;

        // validate
        let errs = validate(&world);
        let errs_str: Vec<String> = errs;
        let want: Vec<&str> = case.validate_errors.to_vec();
        assert_eq!(errs_str.len(), want.len(), "{name}: validate error count");
        for (got, expected) in errs_str.iter().zip(want.iter()) {
            assert_eq!(got, expected, "{name}: validate error text");
        }

        // simulate (MT19937 bit-exact: концовки/тупики/avg_turns совпадают)
        let sim = simulate(&world, 50, 40, 1000);
        assert_eq!(
            canonical(&sim),
            parse(case.simulate).to_string(),
            "{name}: simulate"
        );

        // scripted play (полная дорожка: said/snapshot/avail + состояния)
        let (trace, _final) = scripted_trace(&world, case.seed, case.steps, case.save_at);
        let want_trace = parse(case.trace);
        // сравниваем по шагам, чтобы ошибка была локализована
        let got_trace = trace["trace"].as_array().unwrap();
        let want_steps = want_trace["trace"].as_array().unwrap();
        assert_eq!(
            got_trace.len(),
            want_steps.len(),
            "{name}: trace length (got {} vs want {})",
            got_trace.len(),
            want_steps.len()
        );
        for (i, (g, w)) in got_trace.iter().zip(want_steps.iter()).enumerate() {
            assert_eq!(canonical(g), canonical(w), "{name}: trace step {i}");
        }
        assert_eq!(
            canonical(&trace["final_state"]),
            canonical(&want_trace["final_state"]),
            "{name}: final_state"
        );
        // restore-проверка: состояние из сейва (свежий мир + restore) совпадает
        let restored = trace
            .get("restored_state")
            .and_then(|v| v.as_str())
            .expect("restored_state должен быть");
        assert_eq!(restored, case.restored_state, "{name}: restored_state");
        // отдельная сверка полного состояния (включая 625 слов MT19937)
        assert_eq!(canonical(&_final), case.final_state, "{name}: full state");
    }
}

#[test]
fn golden_ir_compile_and_link() {
    for case in golden_cases::IR_CASES {
        let spec: Value = serde_json::from_str(case.spec).expect("spec");
        if let Some(expected) = case.compile {
            let flat = ir::compile_game(&spec);
            assert_eq!(
                canonical(&flat),
                parse(expected).to_string(),
                "{}: compile",
                case.name
            );
            // скомпилированный мир играбелен валидатором
            assert!(
                validate(&flat).is_empty(),
                "{}: flat world must validate",
                case.name
            );
        }
        let errs = ir::link(&spec);
        let want: Vec<&str> = case.link_errors.to_vec();
        assert_eq!(errs.len(), want.len(), "{}: link error count", case.name);
        for (got, expected) in errs.iter().zip(want.iter()) {
            assert_eq!(got, expected, "{}: link error text", case.name);
        }
    }
}

#[test]
fn golden_rich_play_matches_python() {
    let flat: Value = serde_json::from_str(golden_cases::RICH_FLAT_WORLD).unwrap();
    let (trace, final_state) = scripted_trace(&flat, 5, 20, 8);
    let want = parse(golden_cases::RICH_PLAY);
    assert_eq!(canonical(&trace), canonical(&want), "rich: play trace");
    assert_eq!(
        canonical(&final_state),
        case_final(&want),
        "rich: full state"
    );
}

fn case_final(want: &Value) -> String {
    want["final_state"].as_str().unwrap().to_string()
}
