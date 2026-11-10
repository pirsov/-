## Required Scripts

### Server Scripts
- **src/server/Data/PlayerData.server.luau** -> Player data management using DataStore
- **src/server/Gameplay/Checkpoints.server.luau** -> Checkpoint and respawn logic
- **src/server/Level/Generator.server.luau** -> Level generation with increasing checkpoint gaps

### Shared Scripts
- **src/shared/Gameplay/Remotes.luau** -> RemoteEvent contract for communication between client and server

### Client Scripts
- **src/client/HUD.client.luau** -> HUD displaying timer and checkpoint count
- **src/client/Effects.client.luau** -> Sound effects and UI polish

# RemoteEvents Contract

Implemented in `src/shared/Gameplay/Remotes.luau` (folder `ReplicatedStorage.Remotes`):

| RemoteEvent | Direction | Payload |
|-------------|-----------|---------|
| Checkpoint | Client → Server | (reserved) |
| CheckpointReached | Server → Client | `idx: number` |
| UpdateLeaderboard | Server → Client | `{ entries }` (Plus) |
| CoinCollected | Server → Client | `total: number` (Plus, Phase 32) |

## Player attributes
- `Checkpoint` (number) — last reached index
- `Score` (number) — run score
- `Coins` (number) — Plus
