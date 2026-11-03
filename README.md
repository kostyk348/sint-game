<div align="center">

# sint-game

![ci](https://github.com/kostyk348/sint-game/actions/workflows/ci.yml/badge.svg)
![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
[![Rust core](https://img.shields.io/badge/Rust-sintgame%20core-orange)](#the-rust-core-sintgame)
[![golden-verified](https://img.shields.io/badge/golden--verified-vs%20Python-22c55e)](#the-rust-core-sintgame)
[![Release](https://img.shields.io/github/v/release/kostyk348/sint-game?sort=semver&color=blue)](https://github.com/kostyk348/sint-game/releases)
[![Last commit](https://img.shields.io/github/last-commit/kostyk348/sint-game?branch=main)](https://github.com/kostyk348/sint-game/commits/main)

**A deterministic engine for text LLM games.** The LLM compiles a scenario from
the lore and writes the prose — but the world state is changed only by ordinary
code, through **gates**. Hence: no invented numbers, reproducible saves,
testable balance, cheap content generation.

The problem class is AI-RPG / interactive fiction like Pax Historia or
Character.ai, but with an architecture where **the LLM holds no state**.

> In two words: **the LLM proposes — the gates and the kernel decide.**

English · [Русский](README.ru.md)

</div>

---

## 1. The problem

Chat bots "play a role" with text. The state (gold, HP, NPC attitudes, plot
facts) lives in the context window — it **gets truncated, forgotten and
hallucinated**. Hence the classics: "the sword is suddenly +7", "the NPC
forgot you betrayed him", "you had 50 gold, now you have 300".

## 2. The solution

Split the work between the stochastic and the deterministic:

| Layer | Who does it | Deterministic? |
|---|---|---|
| **World compilation** (lore → rules) | LLM (offline) | no, but the result is **frozen** and reviewed |
| **State and rules** | the kernel (code) | **yes**, seeded |
| **Prose** (the shell) | LLM (runtime) | no, but **touches no state** |
| **Intent** (free text → action) | LLM (runtime) | no, but passes **the gates** |

```
PHASE 1 — COMPILATION (once)              PHASE 2 — RUNTIME (every turn)
  lore.md                                   player input
    │                                          │
    ▼                                          ▼
  LLM ──► world.json ──► VALIDATOR          LLM: intent ──► GATES ──► kernel (state)
                            │ pass                              │
                            ▼                                   ▼
                       a playable world                     LLM: prose ──► text
```

## The Rust core (sintgame)

The deterministic part of the engine — the part that truly wants to be GIL-free
with hard memory — is ported to the Rust crate `sintgame` (the only dependency
is `serde_json`; the world format is JSON):

| Module | Python | What it is |
|---|---|---|
| `src/rng.rs` | `random.Random` | MT19937 **bit-exact with CPython**: saves and playouts are compatible both ways |
| `src/world.rs` | `kernel.py` | conds/effects, trigger cascade, `state()/restore()` in the Python format |
| `src/ir.rs` | `ir.py` | lowering of state machines / time / agents + spec linking |
| `src/schema.rs` | `schema.py` | validator + `stability`/`simulate` |

**Golden verification**: `cargo test` runs 4 example worlds (campaign, sandbox,
station, lighthouse) and a rich IR spec through both cores — turn traces,
state snapshots, full saves (including the 625 MT19937 words), `simulate`
results (endings/dead-ends/avg_turns), validator and link errors, and the IR
compiler output must match byte for byte.

Not ported (on purpose): the LLM glue — `chat/gen/prompt` (HTTP adapters),
`serve`, `editor`, `tune` — thin layers around external APIs; Rust adds
nothing there. Golden regeneration: `python3 scripts/sintgame_golden.py &&
python3 scripts/sintgame_make_golden_tests.py`.

## 3. Quick start

Python ≥ 3.9 required. The kernel is pure stdlib — no dependencies, nothing to
install. The LLM (lore compilation, prose, free-text parsing) plugs in
externally via `SINT_GEN_CMD` and **is not needed to run the example**.

### 3.1. An out-of-the-box world example: `examples/lighthouse`

Four commands from clone to the end of the run. Each was verified on a clean
environment — Python 3.14.7, empty cache, `SINT_GEN_CMD` unset, network used
only at step 2:

```bash
# 1) clone

git clone https://github.com/kostyk348/sint-game.git && cd sint-game

# 2) install: provides the `sintgame` command (you can skip this and call `python3 -m sintgame`)

python3 -m venv .venv && .venv/bin/pip install .

# 3) world check: schema, invariants and witness-based ending reachability

.venv/bin/sintgame validate examples/lighthouse/world.json

# 4) the full playthrough: four actions → the "truth" ending. No LLM, no network.

.venv/bin/sintgame play examples/lighthouse/world.json \
       --script talk_iya,press_marek,search_cabin,reveal_truth --prose none
```

Step 3 prints:

```
VALIDATOR: OK
SIMULATION: {"endings_reached": {"exile": 159, "ice": 69, "truth": 46, "mercy": 26}, "dead_ends": 0, "unstable": 0, "no_ending": 0, "trials": 300, "avg_turns": 11.0}
reachability: ALL 4 declared endings REACHABLE (witness = proof), states=2067
```

Step 4 prints the world's prose and ends with:

```
== END: truth | hp=20 hp_max=20 cold=10 warmth=13 | flags=[journal_found,marek_confessed]
```

`--prose none` is the no-LLM mode: the text comes from the world itself, no
generation is called, and the state and ending are the same as with an LLM
(prose has no access to state by design). The same run with LLM prose is
4 model requests, ~1 min 40 s — see [`docs/COST.md`](docs/COST.md).

Free text ("play it in your own words") requires an LLM and goes through the gates:

```bash
SINT_GEN_CMD="opencode run --pure" \
  .venv/bin/sintgame play examples/lighthouse/world.json --free "hug Iya, she is crying"
```

The other worlds — `station`, `campaign` (a long campaign), `sandbox` (an open
world without endings): what to do with which — [`examples/README.md`](examples/README.md).

### 3.2. The other commands

```bash
# compile your own world from lore (needs an LLM):

sintgame compile examples/lighthouse/lore.md -o my_world.json

# generate content into a world (NPC/item/location/quest) under verification:

sintgame add examples/lighthouse/world.json --kind npc -n 2 -o enriched.json

# local web UI: an RPG (primary) + chat (secondary) — open in a browser:

sintgame serve --port 8000        # → http://127.0.0.1:8000 (RPG), /chat — characters

# author tools:

sintgame editor examples/lighthouse/world.json -o editor.html   # HTML editor + graph
sintgame balance examples/lighthouse/world.json --trials 3000  # ending distribution
sintgame tune examples/station/world.json -o tuned.json        # auto-tuning numbers
sintgame run examples/lighthouse/world.json --turns 60         # a 60-turn run
sintgame sandbox examples/campaign/world.json --turns 500      # an open 500-turn run
sintgame compile examples/sandbox/lore.md -o open.json --sandbox  # a world without endings

# long-term memory between sessions:

sintgame play examples/lighthouse/world.json --save session.json   # save game + memory
sintgame play examples/lighthouse/world.json --load session.json   # continue later
sintgame memory session.json                                       # what the game remembers
```

Tests (offline, no network, no LLM): `make test` or `python -m pytest -q` —
**82 tests**. Only `pytest` is needed: `pip install -e ".[dev]"` (the engine
itself has no runtime dependencies — `pip show sint-game` shows an empty
`Requires`).

## 4. What already works

- **World compiler**: `lore.md → world.json` via an LLM, the output passes the
  validator (up to 3 fix rounds driven by the errors). Both examples compiled
  **on the first pass**.
- **Deterministic kernel**: entities/attributes/flags/items/relations/triggers/
  actions/endings.
- **Validator**: schema + invariants + **exact reachability analysis** (BFS
  with witnesses: a concrete action sequence to every ending + static search
  for dead preconditions "a flag is required but never set").
- **Two-level gates**: structural (schema, bounds, no new endings) + author
  invariants (`constraints.vital`).
- **Free input**: the LLM parses text into an intent → a known action, or
  **proposes a new one** that must pass the gates; it is matched against
  existing actions (no duplicate spam) and **degrades offline** (matching
  works without an LLM).
- **Prose** from the LLM, in tone, **contextual**: connected to the latest
  events (`--context N`), picks up descriptions of mentioned entities.
- **Content creation**: `sintgame add` — generating NPCs/items/locations/quests
  into an existing world; every addition is verified (schema + dead
  preconditions + preserved ending reachability).
- **Long memory** (`memory.py`): facts (only scene-relevant ones go into the
  prompt) + character voices (`voice`) — for coherence over 50+ turns without
  bloating the prompt. State, facts and history **survive restarts**
  (`--save`/`--load`, [`docs/MEMORY.md`](docs/MEMORY.md)).
- **Compaction** (`sintgame compact`): fold the accumulated runtime actions
  back into the world (v2) and re-validate. **Diagnostics** (`sintgame
  diagnose`): which attributes blow up the state space. **Cost** — see
  [`docs/COST.md`](docs/COST.md).
- **Self-explaining gates** (`sintgame why`): every precondition of an action
  evaluated against the live state with actual values — "UNAVAILABLE because
  `iya.trust >= 10` (current: 0)" instead of a bare refusal; the LLM intent
  layer and the prose layer can react to the specific block (`--json`).
- **Counterfactual gate attribution** (`sintgame blame`): which gate blocks an
  ending — the world is relaxed one gate at a time and re-simulated **on the
  same seeds** (paired, not noisy); the report ranks gates by the ending's
  reach-rate gain. On the station example: `капсула_рейна` sits at 0.2% and is
  unlocked (+50%) by removing `launch_rein.pre ["flag","rein_confessed"]` —
  measurement, not guesswork. Deterministic end to end.
- **Author tools** ([`docs/TOOLING.md`](docs/TOOLING.md)): the **editor**
  (`sintgame editor` — a self-contained HTML with a dependency graph and
  witnesses), **balance** (`balance`), **why** (`why`), **blame** (`blame`),
  **tuning** (`tune` — automatic number fitting), **runs** (`run --turns N` —
  multi-episode soaks with invariant checks).
- **Open worlds and long campaigns**: a sandbox without mandatory endings
  (`compile --sandbox`), continuous 500+ step runs (`sandbox`), an optional
  **director** that injects events at runtime under the gates (a Pax Historia
  style mechanic).
- **Stability validator**: catches trigger loops (the cascade hits the guard) —
  otherwise the compiler could assemble a world that breaks on turn one.
- **Local web UI** (`sintgame serve`): an **RPG in the browser** — world
  selection, state, available actions and free input, **long memory**
  (session save/load). Plus a secondary character chat at `/chat`. Stdlib
  HTTP, local, no cloud.
- **Deterministic replay** + a `--variety` mode (liveliness over copies).
- **Full state saving, including the `rng`** (otherwise save/load desyncs).
- **Prompt-cache discipline**: a stable prefix so the model's prompt cache
  stays warm.

## 5. Honest limitations

- This is an **engine core**, not a shipped game. Content (worlds, lore,
  balance) is on the author.
- Ending reachability is **proven by a witness** (BFS); with numeric attributes
  a full exhaustion of the state space is not always possible (threshold
  abstraction is needed, see `docs/ROADMAP.md`) — "not found" is then honestly
  marked as unverified.
- The LLM parts are **seconds**, not milliseconds; only the kernel is
  milliseconds.
- Intent collapses into a closed action dictionary: "hug" may become "talk" if
  there is no such action or proposal.
- Long-run character voice consistency is unverified.
- Number balance is the author's responsibility, not the LLM's.

## 6. Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the kernel, gates, caches, determinism.
- [`docs/FOR-AUTHORS.md`](docs/FOR-AUTHORS.md) — how to make your own game from lore.
- [`docs/COMPILER.md`](docs/COMPILER.md) — how the lore compiler works.
- [`docs/GATE.md`](docs/GATE.md) — the safety model: why "no" is a feature.
- [`docs/CACHE.md`](docs/CACHE.md) — two caches: prose/intent and the model's prompt cache.
- [`docs/COST.md`](docs/COST.md) — tokens per turn and how to cut them (6×).
- [`docs/MEMORY.md`](docs/MEMORY.md) — long memory (state + facts between sessions).
- [`docs/TOOLING.md`](docs/TOOLING.md) — editor, balance, tuning, runs, sandbox.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — what exists, what doesn't, what's next.

## 7. License

MIT — see [`LICENSE`](LICENSE).
