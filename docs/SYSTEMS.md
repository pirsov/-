# Systems (week baseline)

## Remotes (`ReplicatedStorage.Gameplay.Remotes` → folder `ReplicatedStorage.Remotes`)

| Name | Direction | Payload |
|------|-----------|---------|
| Checkpoint | Client→Server | reserved |
| CheckpointReached | Server→Client | `idx: number` |
| UpdateLeaderboard | Server→Client | stub |
| CoinCollected | Server→Client | `totalCoins: number` |

## Player attributes
| Attribute | Type | Meaning |
|-----------|------|---------|
| Checkpoint | number | last CP index |
| Coins | number | run coins |
| Score | number | reserved score |
| BestTime | number | best run seconds (0 = none) |
| RunStartedAt | number | `os.clock()` at spawn (server) |

## Modules
- `Checkpoints.server` — Touched CP, SetAttribute idx, FireClient, LoadCharacter on Died
- `Coins.server` — Touched coin parts in `workspace.Coins`
- `Generator.server` — builds CP + coins from `Content.LevelConfig`
- `Void.server` — Y < −20 → LoadCharacter
- `Puzzles.server` — pressure plate / gate
- `PlayerData.server` — DataStore v2 load/save + BestTime on leave

## BestTime persistence
On `PlayerRemoving`, if `RunStartedAt` is set, `elapsed = os.clock() - RunStartedAt`. If `BestTime == 0` or `elapsed < BestTime`, set `BestTime = elapsed`, then save via pcall DataStore.
