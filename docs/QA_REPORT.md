## BUGS
- [HIGH] src/server/Gameplay/Checkpoints.server.luau:47 — On `Humanoid.Died`, script `task.wait(2)` then teleports `plr.Character`. Roblox usually destroys/replaces the character on death, so HRP is often nil and teleport is a no-op. Suggested fix: after death call `plr:LoadCharacter()` (or wait for next `CharacterAdded`) then move the new HRP to the checkpoint CFrame.
- [MED] src/server/Gameplay/Checkpoints.server.luau:13 — `Touched` has no debounce; one step can fire CheckpointReached many times (spam to client/sound). Suggested fix: per-player cooldown or only fire when `idx` actually increases (already partly gated) plus a short debounce attribute.
- [MED] src/server/Level/Generator.server.luau vs Checkpoints — Generator clears/rebuilds checkpoint parts; Checkpoints hooks existing children at start. If Generator runs after Checkpoints without `ChildAdded` race win, OK because ChildAdded exists — verify Script run order in Studio Output.
- [LOW] src/client/HUD.client.luau — timer starts on LocalScript load, not on “run start”; respawn does not reset timer (may be intended).
- [LOW] src/shared/Gameplay/Remotes.luau — `Checkpoint` remote is created but unused by server/client (dead contract until wired).

## SUGGESTIONS
- PlayerData already uses pcall + `task.wait(60)` — keep; optionally persist best time.
- GDD still lists puzzles/coins/boss — not implemented yet (Phase 32+), not a code defect.
- Add void/kill-brick handling (Phase 34) instead of relying only on Humanoid.Died.

## TEST CASES
- Touch Checkpoint3 then Checkpoint1 — attribute must stay 3; HUD shows CP: 3.
- Die after Checkpoint2 — character should appear above Checkpoint2 (currently often fails — HIGH bug).
- Rejoin server — Score/Checkpoint load from DataStore without error in Output.
- `rojo build` / open place — no red errors from Remotes/HUD/Effects require paths.

## SCORE
- overall: 72
- note: MVP skeleton is coherent after repair; score held down by broken death-teleport and missing GDD systems (puzzles/coins). False CRIT about "PlayerRespawn" from older hallucinated QA is invalid — that API/event is not in the repaired sources.
