# Legacy pitfalls — `legacy_project`

Generated: 2026-11-10T12:00:05.308559+00:00
Findings: **8**

This report lists where the code can break or be abused — not how it works.

## CRIT (3)

### P001 — DataStoreService on client
- File: `src/client/ShopUI.client.luau:6`
- Why: Clients must not touch DataStore — exploit + replication risk.
- Snippet: `local DataStoreService = game:GetService("DataStoreService")`

### P004 — DataStore GetAsync without pcall
- File: `src/server/PlayerData.server.luau:9`
- Why: DataStore failures throw; without pcall the script dies and progress is lost.
- Snippet: `local data = store:GetAsync("u_" .. player.UserId)`

### P005 — DataStore SetAsync without pcall
- File: `src/server/PlayerData.server.luau:17`
- Why: DataStore failures throw; without pcall the script dies and progress is lost.
- Snippet: `store:SetAsync("u_" .. player.UserId, coins)`

## HIGH (2)

### P006 — while true do without wait
- File: `src/server/PlayerData.server.luau:27`
- Why: Tight loop freezes the Luau VM / hangs the server or client.
- Snippet: ``

### P007 — OnServerEvent handler without arg validation
- File: `src/server/Shop.server.luau:21`
- Why: Missing typeof/assert opens an exploit path (free items, illegal packs).
- Snippet: `BuyPack.OnServerEvent:Connect(function(player, packId)`

## MED (3)

### P002 — Client FireServer — ensure server validates args
- File: `src/client/ShopUI.client.luau:14`
- Why: Any client can spoof FireServer args. Server must validate pack/price/ownership.
- Snippet: `BuyPack:FireServer("VIP_UNLIMITED")`

### P003 — GetPlayerFromCharacter without nil guard
- File: `src/server/Checkpoints.server.luau:17`
- Why: Character may be orphaned after leave; nil player crashes handlers.
- Snippet: `local plr = Players:GetPlayerFromCharacter(char)`

### P008 — Deprecated wait() — use task.wait
- File: `src/server/Shop.server.luau:30`
- Why: Global wait is throttled/deprecated; prefer task.wait.
- Snippet: `wait(5)`
