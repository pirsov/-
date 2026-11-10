# Старт 24h — финальный гайд (A16.0)

Фоновый автономный цикл Quality Forge: Planner → Gate → генерация (14B + SEARCH/REPLACE) → Validator (R001/R004/R006), с паузой `waiting_human` без жжения CPU.

**Контекст (A15):** `num_predict≤1024` (diff/repair `512`), semantic prune бандла, компакция стейта на локальной **7B**.

## 0. Подготовка (один раз)

```bash
git pull
# после мержа стека A9…A16 — ветка main или последний merge
# локально достаточно актуального main / merged tip

# ключи (User env)
# DEEPSEEK_API_KEY=...          — HITL / improve goal / TZ
# Ollama локально: ollama serve
#   ollama pull qwen2.5-coder:14b-4k
#   ollama pull qwen2.5-coder:7b-2k   # repair + compact
```

### 0.1. Env flags (A13/A15)

| Переменная | Default | Смысл |
|------------|---------|--------|
| `FORGE_TOKEN_ECONOMY` | `1` | EN + short keys в `bundle_for_14b` |
| `FORGE_NUM_PREDICT` | `1024` | Потолок вывода Ollama (код) |
| `FORGE_NUM_PREDICT_DIFF` | `512` | Потолок для repair/PATCH |
| `FORGE_COMPACT_7B` | `1` | Суммаризация compact_state на 7B |
| `FORGE_JSON_PRETTY` | off | Pretty JSON на диске (иначе minify) |
| `FORGE_BACKEND` | auto | `ollama` / `stub` / cloud |

### 0.2. LEGO / 3D ассеты (A11.0)

1. Положи модели в **`assets/models/`** (`.glb` `.gltf` `.ldr` `.fbx` `.obj`)
2. Сканер:

```bash
python -m pip install -r requirements.txt   # zstandard — для --scan-place-fruits
python -u run.py --scan-assets
# → assets/catalog/assets.json
# опционально обновить фрукты из .rbxl:
# python -u run.py --scan-place-fruits
```

Gate блокирует `proposed_assets`, которых нет в каталоге.

### 0.3. Doctor + тесты

```bash
python -u run.py --doctor
python -u run.py --bundle-savings   # A13/A15 метрики бандла
python -m unittest discover -s tests -q
```

## 1. Запуск UI

```bash
python -u run.py --ui
# или: python -u run.py --ui --ui-port 8787
```

В консоли сразу печатается **Launch Checklist (A16)**:

```
[OK] Ollama: …
[OK] Skeletons: client_ui, datastore_service, …
[OK] Assets catalog: Apple, …
[OK] Validator rules (active): R001, R004, R006
[OK] Token economy (A15): predict=1024/diff=512
```

Открой: **http://127.0.0.1:8787**  
JSON чеклиста: `GET /api/checklist`

В agent dock:

1. Задача, например: *«Симулятор сбора LEGO-яблок. Ассет Apple. DataStore + UI через RemoteEvents»*
2. Ответь на A/B/C (или Другое)
3. **Старт 24h**

Можно закрыть вкладку — `run.py --ui` продолжает жить. При HITL статус → `waiting_human` (парк).

## 2. Что делает «Старт 24h»

`POST /api/start_24h` → `run_hub.start_24h`:

- цикл ≤ `max_cycles` (UI по умолчанию 48)
- `plan_next` → HITL/verify → `waiting_human` + sleep 1с
- иначе короткий `--week` (`week_max_steps`, default 5)
- 14B пишет **SEARCH/REPLACE** патчи, если файл уже есть (A15)
- Validator гоняет **active** rules (R001/R004/R006)
- пауза `sleep` между циклами

## 3. Где логи и статус

| Что | Где |
|-----|-----|
| Лог 24h loop | `.forge/ui_run/loop24-YYYYMMDD-HHMMSS.log` |
| Лог week burst | `.forge/ui_run/<stamp>.log`, `latest.log` |
| Отчёт week | `.forge/ui_run/latest_report.json` |
| Prompt/response LLM | `logs/<stamp>-<task>-*.txt` |
| Живой статус | `GET /api/status_snapshot` |
| Waiting human | `GET /api/status` → `waiting_human`, `hitl_pack` |
| Checklist | `GET /api/checklist` |
| State / очередь | `state.json` |
| HITL-правила | `knowledge_base.json` → `rules` |
| Контракты | `contracts/` (+ `golden/` после verify) |
| 3D каталог | `assets/catalog/assets.json` |

```bash
curl -s http://127.0.0.1:8787/api/checklist | python -m json.tool
curl -s http://127.0.0.1:8787/api/status_snapshot | python -m json.tool
tail -f .forge/ui_run/latest.log
```

## 4. Безопасная остановка

1. **Стоп 24h** в dock → `POST /api/stop_24h`
2. Или `Ctrl+C` на `run.py --ui`
3. Не `-9` без нужды

## 5. Если застрял в waiting_human

Агент ждёт тебя — CPU не крутится.

- UI: **A / B / C / Другое** → `/api/answer`
- verify плагина: `channel=verify`
- Лог: `grep -n waiting_human .forge/ui_run/loop24-*.log | tail`
- Статус: `curl -s localhost:8787/api/status_snapshot | python -m json.tool | grep -A5 waiting`

## 6. Troubleshooting

### Ollama отвалилась / «runtime backend=stub»

```bash
ollama serve
ollama list
ollama pull qwen2.5-coder:14b-4k
ollama pull qwen2.5-coder:7b-2k
python -u run.py --doctor
# UI: GET /api/health?force=1
```

Пока Ollama down, pipeline уходит в **stub** и **не закрывает** задачи как done — это защита, не баг.

### Перезапуск цикла с места падения

1. Не трогай уже `[x]` в `PROJECT_TZ.md` — week берёт следующие `[ ]`
2. `state.json` хранит `task_queue` / `done` — не удаляй без нужды
3. Снова: `python -u run.py --ui` → **Старт 24h** (или CLI `python -u run.py --week`)
4. Если застрял один таск: посмотри `logs/*-prompt.txt` / `*-response.txt`, поправь TZ вручную или ответь HITL

### Validator режет код (R001/R004/R006)

```bash
python -u run.py --rules-list
# active: R001 (no DS on client), R004 (pcall), R006 (typeof on OnServerEvent)
```

Чини код или (осознанно) оставь draft — не снимай active без причины.

### Бандл / VRAM

```bash
python -u run.py --bundle-savings
# ожидаемо ~20%+ lean; cycle ~0.7–1.3k tok
# FORGE_NUM_PREDICT=512  — ещё жёстче урезать вывод
```

Не поднимай `num_ctx` выше **4096** на 6 ГБ.

### Ассеты «не видит»

```bash
ls assets/models/
python -u run.py --scan-assets
curl -s localhost:8787/api/checklist | python -m json.tool
```

## 7. Что умеет ядро к марафону

| Слой | Доказательство |
|------|----------------|
| Save / Net / Full-stack | A10.1–A10.4 |
| 3D assets Gate | A11.0 |
| Legacy audit → rules | A12 / A14 (`R001/R004/R006` **active**) |
| Token economy | A13 EN+minify |
| Diff + predict caps + prune + 7B compact | A15 |
| Launch checklist | A16 |

game1 polygon **frozen** — новые фичи в `artifacts/` и `contracts/system.*`.

## 8. Быстрый чеклист перед марафоном

- [ ] `unittest` → OK  
- [ ] `ollama list` видит 14b + 7b  
- [ ] `.glb` в `assets/models/` + `--scan-assets`  
- [ ] `--rules-list` → R001/R004/R006 **active**  
- [ ] `python -u run.py --ui` → checklist OK  
- [ ] Знаешь `.forge/ui_run/` и **Стоп 24h**

Удачного автономного прогона.
