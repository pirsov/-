# A10.0 — DataStore & Networking Archetypes (план)

**Контекст:** A9.0 дал UI + `waiting_human` + 24h loop. Ядро (planner → halluc gate → skeletons → validator) уже гоняет `client_ui` / `server_script` / `shared_data` / `network_remote`. В `KNOWN_ARCHETYPES` слот `datastore_service` зарезервирован, но **скелета и META ещё нет** — это бывший A7.3.

**Вывод:** следующим логичным модулем после живого UI является не «ещё один UI-рефактор», а **персистентность + сетевой контракт**, иначе 24h-цикл в фоне будет штамповать плагины без безопасного сохранения прогресса игрока.

---

## Почему не «просто A7.3 в изоляции»

| Уже есть | Дыра для сетевых игр |
|----------|----------------------|
| `network_remote@v1` — whitelist Remotes, forbid DataStore на клиенте | Нет серверного шаблона PlayerData Load/Save |
| Validator режет DataStore в `client_ui` | Нет позитивного контракта «только Server + pcall + session lock» |
| HITL / verify через UI | Нет smoke-вопросов «данные пережили rejoin» |
| 24h loop паркуется на HITL | Нет archetype pin в contracts для `*.PlayerData*` |

A7.3 как один скелет недостаточен: без связки **Remote → Server DataStore → shared schema → gate** агент снова выдумает `GetBestTime` / пишет DataStore в LocalScript.

Поэтому цикл называется **A10.0**, а A7.3 входит в него как подпункт.

---

## Цель A10.0

Чтобы в фоне (кнопка «Старт 24h») агент мог закрывать плагины вида:

- Remotes (сеть)
- PlayerData / inventory (сохранение)
- UI, читающий только attrs / FireServer

…с теми же гарантиями, что A8.0 для donation_ui: gate, bundle ≤ контекста 14B, validator PASS, негативный кейс FAIL.

---

## План по шагам

### A10.1 — Archetype `datastore_service@v1` (бывший A7.3)

- `skeletons/datastore_service/v1/{META.json,SKELETON.luau}`
- META:
  - **require:** `DataStoreService`, `pcall`, `Players.PlayerAdded` / `PlayerRemoving`, server-only path hints
  - **forbid:** `LocalPlayer`, `FireServer`, клиентские ScreenGui
  - **forbid_regex:** прямой `GetAsync`/`SetAsync` вне `pcall`; синхронный yield на критическом пути без debounce (мягко, через rules)
- Registry + `KNOWN_ARCHETYPES` уже содержит id — только активировать
- Pin-by-contract: `contracts/*.player_data.json` → `archetype: datastore_service`

### A10.2 — Networking glue (эволюция, не новый зоопарк)

- Усилить `network_remote@v1` (или `v1.1`): явный whitelist имён Remotes для donate / coins / save-ack
- `shared_data@v1`: схема attrs (`Coins`, `BestTime`, …) как единственный контракт UI↔Server
- Halluc gate: разрешённые exports из PlayerData (`get_player_coins`, `SaveAsync` server) — как в A8 demo

### A10.3 — Validator + knowledge rules

- Позитив: server PlayerData с pcall + leave-save → PASS
- Негатив: DataStore в client / Remote return Folder → FAIL (уже частично есть)
- Опционально `FORGE_RULES_AUTO` шаблоны: «no DataStore on client», «no yield in RemoteEvent handler without task.spawn»

### A10.4 — E2E + UI verify

- Артефакт `artifacts/a10_e2e/`: Remotes + PlayerData + тонкий client HUD
- Через UI: chat «система доната с сохранением монет» → HITL → generate → `/api/answer` channel=verify
- Bundle skills для 14B: archetype cards ≤350 + skeleton budget

### A10.5 (опционально, после A10.1–4) — Studio smoke pack

- Вопросы smoke: rejoin сохранил Coins? BestTime не вырос после death?  
- Питает этап 05 UI и 24h `verify_plugin`

---

## Порядок внедрения (рекомендация)

1. **A10.1** скелет + registry + тесты META (быстрый win, разблокирует pin).
2. **A10.2–A10.3** gate/validator (без этого 24h опасен).
3. **A10.4** E2E как A8.0 — критерий «можно в автономию».
4. A7.1b UI polish / game1 — только после зелёного A10.4.

**Не брать сейчас:** Celery, FastAPI, React, полноценный Matchmaking — память и зависимости важнее скорости итерации.

---

## Критерий готовности A10.0

- [ ] `datastore_service@v1` в registry, `--archetypes-list` показывает
- [ ] Негативный тест: DataStore в client → FAIL
- [ ] Позитивный E2E: server save/load skeleton + remote whitelist → validator PASS, gate не пропускает выдуманные API
- [ ] Из UI: chat → HITL → (опционально) 24h burst не зависает в CPU на `waiting_human`
- [ ] Тесты suite зелёные (цель: +8–12 к текущим 56)

---

## Связь с отложенным

| Было | Куда уходит |
|------|-------------|
| A7.3 datastore_service | **A10.1** |
| A7.1b richer A/B/C UI | После A10.4 (UX, не блокер генерации) |
| game1 polish | По-прежнему frozen; A10 артефакты в `artifacts/`, не ломают polygon |
