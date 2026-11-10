# Quality Forge UI — как пользоваться

Control panel на **stdlib** (`ThreadingHTTPServer` + Vanilla HTML/JS). Без React/FastAPI.

```bash
python -u run.py --ui
# → http://127.0.0.1:8787
```

Требования: Python 3.10+. DeepSeek (`DEEPSEEK_API_KEY`) — для улучшения цели / HITL / TZ. Ollama или Cloud Fallback — для генерации Luau в `--week`.

---

## Что видно на экране

### Agent dock (верх, сразу под «Сейчас»)

| Элемент | Действие |
|---------|----------|
| Поле чата | Enter / «Отправить» → `POST /api/chat` |
| Кнопки **A / B / C / Другое** | Появляются при `waiting_human` → `POST /api/answer` |
| **Старт 24h** | Автономный цикл → `POST /api/start_24h` |
| **Стоп 24h** | Остановка цикла → `POST /api/stop_24h` |
| Прогресс-бар + «плагины · очередь» | Поллинг `GET /api/status_snapshot` |

### Этапы 01–06 (старый поток)

Проект → Цель/skills → TZ → Генерация `--week` → Smoke → Фиксы. Можно пропустить шаги. Работает параллельно с agent dock.

---

## Типичный сценарий

1. Пишешь в чат: *«Сделай простую систему доната с кнопкой»*.
2. Planner / DeepSeek собирает HITL-пакет → статус **`waiting_human`**.
3. В dock появляются вопрос и кнопки A/B/C/Другое.
4. Жмёшь **A** (или Другое + текст) → ответ уходит в `/api/answer`.
5. `waiting_human` снимается; дальше можно жать **Старт 24h** или этап 04 «Старт генерации».

Вкладку браузера можно закрыть: воркер живёт в процессе `run.py --ui`. Если агенту нужен ответ — он **паркуется** в `waiting_human` и не крутит CPU, пока снова не откроешь UI и не ответишь.

---

## API (`forge/api_hub.py` + роуты в `ui_server.py`)

### Agent bridge

| Метод | Путь | Тело / ответ |
|-------|------|----------------|
| `POST` | `/api/chat` | `{ "message": "...", "project": "game1" }` → цель, HITL-pack или `verify_plugin`, статус `waiting_human` / `ready` |
| `POST` | `/api/answer` | HITL: `{ "answer": "Q1=A" }` или `{ "answers": {"Q1":"A"} }`. Verify: `{ "channel":"verify", "plugin":"game1.hud", "verdict":"y" }` |
| `POST` | `/api/start_24h` | `{ "sleep": 30, "max_cycles": 48, "week_max_steps": 5 }` → фоновый `loop_24h` |
| `POST` | `/api/stop_24h` | `{}` → стоп цикла + SIGTERM дочернего `--week` при наличии |
| `GET` | `/api/status_snapshot` | плагины closed/verified, очередь, `hitl_pack`, `run`, флаг `waiting_human` |
| `GET` | `/api/status` | прежний статус UI + поле `snapshot` (то же обогащение) |

### Уже существовавшие (этапы 01–06)

`/api/health`, `/api/progress`, `/api/goal/improve`, `/api/skills/auto`, `/api/tz`, `/api/run/start`, `/api/run/status`, `/api/smoke/*`, `/api/fix/*`, …

---

## Статус `waiting_human`

Когда агент задал вопрос (HITL pack или verify плагина):

1. `run_hub.set_waiting_human(reason=..., detail=...)` → `status = "waiting_human"`.
2. Цикл 24h **не** спавнит `--week` и **не** жжёт CPU: sleep по 1 с, пока статус не сменится или не придёт stop.
3. UI показывает pack / verify-hint; поллинг snapshot продолжается.
4. После `/api/answer` без follow-up → `clear_waiting_human()` → `idle` (или снова `looping`, если 24h ещё активен).
5. Если «Другое» породило новый уточняющий pack → снова `waiting_human`.

Причины (`waiting_reason`): `hitl_pack` | `hitl_clarify` | `verify_plugin` | `ask_hitl` (из loop).

---

## Кнопка «Старт 24h»

Запускает `run_hub.start_24h` в daemon-thread:

```
цикл ≤ max_cycles:
  если waiting_human → sleep (парк)
  иначе plan_next()
    ask_hitl / verify_plugin → set_waiting_human, continue
    иначе короткий --week (subprocess, week_max_steps)
  пауза sleep секунд между циклами
```

- UI не блокируется (`ThreadingHTTPServer` + thread).
- Прогресс: `plugins_closed` / `queue_pending` + `loop_cycle` / `loop_max`.
- **Стоп 24h**: `_stop_event`, статус → `idle`, попытка `SIGTERM` на pid `--week`.

Параметры по умолчанию в UI: `sleep=5`, `max_cycles=48`, `week_max_steps=5` (короткие бёрсты, удобно для проверки).

---

## Файлы

| Путь | Роль |
|------|------|
| `forge/api_hub.py` | Логика эндпоинтов |
| `forge/ui_server.py` | HTTP-роуты + статика `ui/` |
| `forge/run_hub.py` | week subprocess + waiting_human + loop_24h |
| `ui/index.html` / `app.js` / `styles.css` | Agent dock + этапы |
| `tests/test_api_hub.py` | Юнит-тесты с моками planner/feedback |

Отчёт A9.0: `artifacts/a9_ui/report.json`. План следующего этапа: [`docs/A10_PLAN.md`](docs/A10_PLAN.md).
