## BUGS
- [HIGH] src/server/Gameplay/Checkpoints.server.luau — (FIXED in repo) death teleport via old Character was a no-op; now uses LoadCharacter + CharacterAdded teleport.
- [MED] Touched debounce — (FIXED) 0.35s per-player debounce added.
- [LOW] src/shared/Gameplay/Remotes.luau — `Checkpoint` remote still unused (reserved).
- [LOW] HUD timer does not reset on respawn (may be intended).

## FALSE POSITIVES (ignore — from earlier hallucinated QA)
- PlayerRespawn / "alive before updating checkpoint" — not real bugs in repaired sources.

## SUGGESTIONS
- Phase 32+: coins, puzzles, LevelConfig per GDD depth layers.
- Prefer concrete stud distances in GDD (e.g. gap 50/70/90), not "100 units".

## TEST CASES
- Touch Checkpoint3 then 1 — attribute stays 3; HUD CP: 3; sound once (debounce).
- Die after Checkpoint2 — new character spawns at Checkpoint2 +Y5.
- Remotes module returns table; HUD/Effects require path works.

## SCORE
- overall: 82
- note: After manual Checkpoints repair (LoadCharacter path). Do NOT accept refactorer stubs that invent PlayerRespawn or delete Touched.
