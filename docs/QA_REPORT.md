## BUGS
- [CRIT] src/server/Gameplay/Checkpoints.server.luau: Line 10 - PlayerRespawn event does not handle player death correctly. Suggested fix: Add a check to ensure player is alive before respawning.
- [CRIT] src/server/Gameplay/Checkpoints.server.luau: Line 20 - CheckpointReached event does not handle player death correctly. Suggested fix: Add a check to ensure player is alive before updating checkpoint data.

## SUGGESTIONS
- Add error handling for DataStore operations in src/server/Data/PlayerData.server.luau and src/server/Gameplay/Checkpoints.server.luau.
- Implement a more robust respawn system that handles player death and respawn logic.

## TEST CASES
- Test player death and respawn in Studio.
- Test checkpoint handling and respawn logic in Studio.
- Test leaderboard functionality in Studio.
