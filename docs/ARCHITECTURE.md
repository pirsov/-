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

## Player Actions
- **PlayerRespawn**: Player has respawned.
  - Payload: `{ player: Player }`

- **PlayerCheckpoint**: Player has reached a checkpoint.
  - Payload: `{ player: Player, checkpointId: number }`

## Game Events
- **GameStart**: Game has started.
  - Payload: `{ startTime: number }`

- **GameEnd**: Game has ended.
  - Payload: `{ endTime: number, winner: Player }`
