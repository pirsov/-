---
name: forge-player-attrs
source: forge-learned
max_chars: 900
---
# Player attributes (KEEP SHORT)

- Set/read Score, Checkpoint, Coins, BestTime on **Player** (`plr:SetAttribute` / `player:GetAttribute`).
- NEVER `character:GetAttribute("Coins")` — Character attrs stay nil and wipe HUD each frame.
- Remotes whitelist only: Checkpoint, CheckpointReached, UpdateLeaderboard, CoinCollected.
- NEVER invent `CoinsCollected`.
- Coins: `coin:Destroy()` then `plr:SetAttribute("Coins", n)` then FireClient + FireAllClients UpdateLeaderboard.
- LevelConfig: Luau `id = n` only (never JS `id:`).
- Spawn: `Instance.new("SpawnLocation")` not Part renamed.
