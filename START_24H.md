# Старт 24h — финальный гайд

Фоновый автономный цикл Quality Forge: Planner → Gate → генерация → Validator, с паузой `waiting_human` без жжения CPU.

## 0. Подготовка (один раз)

```bash
git pull
# ветка со стеком A9→A10, либо main после мержа
git checkout cursor/a10-3-4-fullstack-9409   # или актуальная после merge

# ключи (User env)
# DEEPSEEK_API_KEY=...          — HITL / improve goal / TZ
# Ollama локально ИЛИ Cloud Fallback (FORGE_BACKEND / OpenRouter)
```

Проверка:

```bash
python -u run.py --doctor
python -m unittest discover -s tests -q
```

## 1. Запуск UI

```bash
python -u run.py --ui
```

Открой: **http://127.0.0.1:8787**

В agent dock (верх):

1. Напиши: *«Сделай игру про сбор монет с сохранением»* → Enter  
2. Ответь на A/B/C (или Другое)  
3. Нажми **Старт 24h**

Можно закрыть вкладку — процесс `run.py --ui` продолжает жить. Если агенту нужен ответ, статус станет `waiting_human` (парк, не CPU-spin).

## 2. Что делает «Старт 24h»

`POST /api/start_24h` → `run_hub.start_24h`:

- цикл ≤ `max_cycles` (в UI по умолчанию 48)
- `plan_next` → при HITL/verify → `waiting_human` + sleep по 1с
- иначе короткий `--week` subprocess (`week_max_steps`, по умолчанию 5)
- пауза `sleep` между циклами

Параметры UI: `sleep=5`, `max_cycles=48`, `week_max_steps=5`.

## 3. Где логи и статус

| Что | Где |
|-----|-----|
| Лог 24h loop | `.forge/ui_run/loop24-YYYYMMDD-HHMMSS.log` |
| Лог week burst | `.forge/ui_run/<stamp>.log`, `latest.log` |
| Отчёт week | `.forge/ui_run/latest_report.json` |
| Живой статус | `GET http://127.0.0.1:8787/api/status_snapshot` |
| Run pill | `GET /api/run/status` или chip в UI |
| State / очередь | `state.json` |
| HITL-правила | `knowledge_base.json` → `rules` (`active`/`draft`) |
| Контракты | `contracts/` (+ `contracts/golden/` после verify «y») |

Пример:

```bash
curl -s http://127.0.0.1:8787/api/status_snapshot | python -m json.tool
tail -f .forge/ui_run/latest.log
```

В UI: прогресс «плагины · очередь», статус `looping` / `waiting_human` / `idle`.

## 4. Безопасная остановка

1. Кнопка **Стоп 24h** в dock → `POST /api/stop_24h`  
   - ставит `_stop_event`  
   - пытается `SIGTERM` на pid `--week`  
   - статус → `idle`
2. Или в терминале: `Ctrl+C` на процессе `run.py --ui` (остановит и HTTP, и фоновые threads).
3. Не убивай `-9` без нужды — лучше дать week завершиться или получить SIGTERM.

Проверка после стопа:

```bash
curl -s http://127.0.0.1:8787/api/run/status
# status: idle, mode: null
```

## 5. Если застрял в waiting_human

Агент ждёт тебя — CPU не крутится. Открой UI:

- кнопки **A / B / C / Другое** → `/api/answer`
- или verify плагина: ответ с `channel=verify`

Пока нет ответа, 24h loop только спит в парке.

## 6. Что уже умеет ядро (к старту 24h)

| Слой | Архетип | Доказательство |
|------|---------|----------------|
| Save | `datastore_service@v1` | A10.1 `system.player_save` |
| Net | `network_remote@v1.1` | A10.2 `system.coin_sync` |
| UI+FireServer | `client_ui@v1.1` | A10.4 `system.donation_shop` |
| HITL rules | forbid RunStartedAt в UI/Remotes | A10.3 |
| Full-stack | UI → DonateRequest → DataStore → CoinSync | A10.4 |

game1 polygon по-прежнему **frozen** — новые фичи копятся в `artifacts/` и `contracts/system.*`.

## 7. Быстрый чеклист перед марафоном

- [ ] `python -m unittest discover -s tests -q` → OK  
- [ ] DeepSeek ключ или осознанный stub/fallback  
- [ ] `python -u run.py --ui` слушает `:8787`  
- [ ] Знаешь, где `.forge/ui_run/`  
- [ ] Знаешь кнопку **Стоп 24h**

Удачного автономного прогона.
