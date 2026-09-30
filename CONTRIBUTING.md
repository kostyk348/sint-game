# Contributing

## Запуск

```bash
pip install -e ".[dev]"
python -m pytest -q
```

Тесты **оффлайн**: LLM и сеть не нужны. Команды `compile` и `play --free/--prose llm`
требуют `SINT_GEN_CMD` (по умолчанию `opencode run --pure`).

## Перед PR

```bash
python -m pytest -q
python -m sintgame validate examples/lighthouse/world.json
python -m sintgame validate examples/station/world.json
```

## Принципы

1. **Состояние меняет только код.** Любое предложение LLM проходит ворота (`gate`).
2. **Детерминизм по seed.** Только ядро детерминировано; проза/интент — нет, но не влияют
   на реплей благодаря кэшам и провенансу.
3. **Всё, что можно проверить оффлайн — проверяется тестом.** Тесты не должны требовать LLM.
4. **Честность важнее красоты.** «Не найдено» не выдаётся за «недостижимо», если поиск
   не исчерпал пространство (см. `search.py`).

## Как добавить мир

См. [`docs/FOR-AUTHORS.md`](docs/FOR-AUTHORS.md). Коротко: `lore.md` → `sintgame compile`
→ проверь `sintgame validate` (жди свидетелей достижимости) → положи в `examples/`.

## Стиль

- Python ≥ 3.9, только стандартная библиотека в рантайме.
- Длина строки ≤ 110 (`pyproject.toml` → `[tool.ruff]`).
- Каждый новый инвариант ворот — тест в `tests/test_gate.py`.
