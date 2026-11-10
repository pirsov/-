# A10.0 — DataStore & Networking Archetypes (план)

**Контекст:** A9.0 дал UI + `waiting_human` + 24h loop. A10 закрывает персистентность и сеть, без которых автономный цикл штампует «красивые, но забывчивые» плагины.

---

## Статус

| Шаг | Статус |
|-----|--------|
| **A10.1** `datastore_service@v1` | ✅ PASS — `artifacts/a10_e2e/`, 64→… tests |
| **A10.2** networking glue | ✅ PASS — `network_remote@v1.1` + `system.coin_sync` |
| A10.3 validator/knowledge rules | ⏳ next |
| A10.4 full-stack E2E + UI verify | ⏳ |
| A10.5 Studio smoke pack | optional |

game1 polygon — **frozen** (артефакты только в `artifacts/`).

---

## A10.1 — Archetype `datastore_service@v1` ✅

- META: require `DataStoreService` / `GetDataStore` / `pcall`; forbid UI
- E2E `system.player_save`; client DataStore → FAIL; галлюцинации blocked
- Legacy `game1.player_data` остаётся `server_script` (Studio attrs-only)

## A10.2 — Networking glue ✅

**Сделано:**

1. **`network_remote@v1.1`** (latest остаётся `v1` для game1 pin)
   - require: `getOrCreate`, `RemoteEvent`, `return`, **`CoinSync`**
   - whitelist: `CoinCollected`, `DonateRequest`, `SaveAck`
   - forbid: DataStore / LocalPlayer / FireServer / UI
2. **E2E `system.coin_sync`** (`artifacts/a10_2_e2e/`)
   - `Remotes.luau` — whitelist с CoinSync
   - `CoinSync.server.luau` — `FireClient` пушит Coins
   - `CoinHUD.client.luau` — `OnClientEvent` обновляет ScreenGui
   - `CoinHUD_BAD.client.luau` — DataStore на клиенте → FAIL
3. **`contract_index.gate_plan`**
   - `CLIENT_FORBIDDEN_EXPORTS` (DataStore*) на client_ui / `*.client.luau`
   - forbids **scoped** к `plan.plugin` (не глобально — иначе LocalPlayer ломал UI-планы)
4. Pin scoring: exact relative path > fuzzy name (артефактный Remotes ≠ game1.remotes)

**Связка:** Server attrs/DataStore → `CoinSync:FireClient` → Client HUD. Клиент **не** читает DataStore.

## A10.3 — Validator + knowledge rules (следующий)

- Позитив: server PlayerData с pcall + leave-save → PASS *(частично A10.1)*
- Негатив: DataStore в client / Remote return Folder → FAIL *(есть)*
- Опционально `FORGE_RULES_AUTO`: no yield in RemoteEvent handler without `task.spawn`

## A10.4 — Full-stack E2E + UI verify

- Один прогон: PlayerSave + CoinSync Remotes + CoinHUD
- UI: chat «игра про сбор монет с сохранением» → HITL → generate → verify

## A10.5 (опционально) — Studio smoke

- rejoin сохранил Coins? BestTime после death?

---

## Критерий готовности A10.0

- [x] `datastore_service@v1` в registry *(A10.1)*
- [x] Негативный тест: DataStore в client → FAIL *(A10.1/A10.2)*
- [x] Позитивный E2E save *(A10.1)* + networking CoinSync *(A10.2)*
- [x] Gate: клиентский план с DataStore → blocked *(A10.2)*
- [ ] Из UI: chat → HITL → 24h burst
- [x] Suite зелёный *(73 OK на A10.2)*
- [ ] A10.3 rules + A10.4 full stack

---

## Связь с отложенным

| Было | Куда |
|------|------|
| A7.3 datastore_service | **A10.1** ✅ |
| Networking / Remotes glue | **A10.2** ✅ |
| A7.1b richer A/B/C UI | После A10.4 |
| game1 polish | frozen |
