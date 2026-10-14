# Примеры миров

Четыре готовых мира в формате `world.json`; рядом с каждым — `lore.md`, из которого мир
компилировался (компиляция требует LLM, игра — нет). Все миры можно проверить и пройти
оффлайн, без ключей и без сети:

```bash
python3 -m sintgame validate examples/<мир>/world.json   # схема, инварианты, достижимость
```

## «Из коробки»: `lighthouse` — «Соль»

Маяк на скале, середина зимы, берег отрезан льдом. Это мир, на котором проверялся чистый
старт: одна команда, без установки, без LLM, без сети, без правки файлов.

```bash
git clone https://github.com/kostyk348/sint-game.git && cd sint-game
python3 -m sintgame play examples/lighthouse/world.json \
       --script talk_iya,press_marek,search_cabin,reveal_truth --prose none
```

Концовка, которой это заканчивается (проверено на клоне `d114a7b`):

```
== END: truth | hp=20 hp_max=20 cold=10 warmth=13 | flags=[journal_found,marek_confessed]
```

Дословный вывод `validate` для этого мира — все четыре концовки достижимы **со свидетелем**
(свидетелем доказывается достижимость, а не «нашли случайно»):

```
VALIDATOR: OK
SIMULATION: {"endings_reached": {"exile": 159, "ice": 69, "truth": 46, "mercy": 26}, "dead_ends": 0, "unstable": 0, "no_ending": 0, "trials": 300, "avg_turns": 11.0}
reachability: ALL 4 declared endings REACHABLE (witness = proof), states=2067
  reachable              exile  witness(2): strike_marek -> strike_marek
  reachable              truth  witness(3): press_marek -> search_cabin -> reveal_truth
  reachable                ice  witness(3): wait_out_storm -> wait_out_storm -> wait_out_storm
  reachable              mercy  witness(4): talk_iya -> search_cabin -> ask_lighter -> burn_journal
```

Почему именно он: 13 действий и 11 ходов в среднем — короткий срез, который проходится
целиком за минуту, а 4 концовки показывают все три механики сразу (действия, флаги + триггеры,
числовые атрибуты). С прозой от LLM тот же прогон стоит 4 запроса к модели — `docs/COST.md`.

## Остальные миры

| мир | название | сущностей | действий | концовки | `validate` |
|---|---|---|---|---|---|
| `lighthouse` | Соль | 14 | 13 | `truth`, `mercy`, `exile`, `ice` | ALL 4 REACHABLE, states=2067, avg 11.0 хода |
| `station` | Орбитальная станция «Анемон» | 9 | 12 | `все_остаются`, `правда_наружу`, `капсула_рейна`, `юсуф` | ALL 4 REACHABLE, states=2379, avg 7.3 хода |
| `campaign` | Акра: Караван под бурей | 13 | 37 | `storm`, `silence`, `debt`, `truth` | PARTIAL — поиск упёрся в лимит 50 001 состояния (это **не** доказательство недостижимости); симуляция: `storm` 179, `silence` 74, без концовки 47, avg 81.6 хода |
| `sandbox` | Уэллс на краю пустыни | 16 | 30 | — (мир без концовок) | OPEN WORLD (концовки не объявлены) |

Как с ними работать (все три команды прогнаны, вывод — дословный):

```bash
# Орбитальная станция — вторая история с концовками; полный свидетель капсулы Рейна:
python3 -m sintgame play examples/station/world.json --prose none \
       --script talk_rein,talk_rein,talk_rein,press_rein,offer_deal,launch_rein
# → == END: капсула_рейна | hp=10 hp_max=10 authority=6 evidence=3 | flags=[report_forged,rein_confessed,capsule_busy]

# Долгая кампания — многоэпизодный прогон с проверкой инвариантов:
python3 -m sintgame run examples/campaign/world.json --turns 200
# → soak: 200 turns across 3 episodes (policy=explore, seed=0)
#   endings: {'silence': 1, 'storm': 1}
#   max single episode: 91 turns (эпизоды: [91, 33, 76])
#   violations: 0

# Открытый мир без финала — длинный прогон:
python3 -m sintgame sandbox examples/sandbox/world.json --turns 500
# → sandbox: 500 turns continuous (policy=linger, seed=0)
#   ended: нет (открытый финал)
#   distinct actions used: 27 / 30
#   dead-ends: 0
#   violations: 0
```

## Что здесь не проверяется автоматически

`tests/test_examples.py` прогоняет только `lighthouse` и `station`: они укладываются в лимит
поиска и потому доказывают свои концовки. `campaign` и `sandbox` в тесты не взяты именно
поэтому — у первого пространство состояний не исчерпывается (см. `sintgame diagnose`), у
второго концовок нет по замыслу. `validate` для них по-прежнему зелёный по схеме и инвариантам.
