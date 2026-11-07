## BUGS
- [LOW] src/shared/Gameplay/Remotes.luau — `Checkpoint` remote reserved/unused.
- [LOW] src/client/HUD.client.luau — timer does not reset on respawn (may be intended).

## FALSE POSITIVES
- Ignore any historical mention of PlayerRespawn — not in sources; do not invent it.

## SUGGESTIONS
- Phase 32+: coins, puzzles, LevelConfig with concrete stud gaps (50/70/90).
- Keep Checkpoints Touched + LoadCharacter respawn; never delete for stub remotes.

## TEST CASES
- Touch Checkpoint3 then 1 — attribute stays 3; HUD shows CP: 3.
- Die after Checkpoint2 — respawn at Checkpoint2 +Y5 via LoadCharacter.
- Remotes require path works for HUD and Effects.

## SCORE
- overall: 82
- note: Seeded after QA model loop; safe baseline for Phase 32.
