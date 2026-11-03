//! # sintgame — детерминированное ядро sint-game на Rust
//!
//! «LLM предлагает — ворота и ядро решают»: состояние мира меняет только
//! обычный код через ворота (`cond`/`eff`), LLM состояния не касается.
//!
//! Портировано (golden-verified против Python-прототипа):
//! - [`rng`] — MT19937, бит-в-бит с `random.Random` CPython (сейвы совместимы);
//! - [`world`] — детерминированное ядро `kernel.py`: conds, effects, roll,
//!   каскад триггеров, save/restore в формате Python;
//! - [`ir`] — понижение богатой спеки (машины состояний, время, агенты)
//!   в плоский мир ядра + линковка/тайпчек спеки;
//! - [`schema`] — валидатор мира + stability/simulate (случайные прогоны).
//!
//! Не портировано (тонкая LLM-обвязка): chat/gen/prompt (HTTP-адаптеры),
//! serve (HTTP-сервер), editor, tune, play/CLI-REPL — см. README.

pub mod ir;
pub mod rng;
pub mod schema;
pub mod world;

pub use rng::PyRandom;
