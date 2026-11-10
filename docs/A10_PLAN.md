# A10.0 — DataStore & Networking Archetypes

**Статус: A10.1–A10.4 ✅** — базис для безопасного 24h цикла готов. Гайд: [`START_24H.md`](../START_24H.md).

| Шаг | Статус |
|-----|--------|
| **A10.1** `datastore_service@v1` | ✅ `artifacts/a10_e2e/` |
| **A10.2** networking glue | ✅ `network_remote@v1.1` + `system.coin_sync` |
| **A10.3** HITL rules on archetypes | ✅ RunStartedAt forbid → client_ui + network_remote |
| **A10.4** full-stack E2E | ✅ `system.donation_shop` UI→Remote→DataStore→CoinSync |
| A10.5 Studio smoke pack | optional |

game1 polygon — **frozen**.

---

## A10.3 — Rules E2E ✅

- `draft_rule_from_comment` распознаёт **RunStartedAt** + UI/Remotes
- `match.archetypes`: `client_ui` / `network_remote`
- `submit_verdict(n)` + `FORGE_RULES_AUTO` → active → validator FAIL на утечке в HUD/Remotes

## A10.4 — Full-stack `system.donation_shop` ✅

Planner split (3 задачи):

| Part | Archetype | Role |
|------|-----------|------|
| Remotes | `network_remote@v1.1` | `DonateRequest` / `CoinSync` / `SaveAck` |
| Server | `datastore_service@v1` | `OnServerEvent` + pcall Get/SetAsync |
| Client | `client_ui@v1.1` | кнопки + `FireServer` (DataStore всё ещё forbid) |

Gate: каждый part enqueue; клиентский DataStore / remotes GetAsync → blocked.  
Артефакты: `artifacts/a10_4_e2e/`.

## Критерий готовности A10.0

- [x] datastore_service + client DataStore FAIL
- [x] CoinSync networking + client DataStore gate
- [x] HITL rules на полных архетипах
- [x] Full-stack donation_shop
- [x] Suite зелёный (**78 OK**)
- [x] `START_24H.md`
- [ ] Desktop: человек жмёт «Старт 24h» (H14)
