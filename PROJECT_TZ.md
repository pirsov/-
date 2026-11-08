# LAST_UPDATE: 2026-11-08 FRESH RUN from zero
# FORGE: LLM writes the game. Cursor = forge only.
# RUN (PowerShell):
#   $env:FORGE_BACKEND = "ollama"
#   Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue
#   .\scripts\reset-week.ps1
#   python run.py --doctor
#   python run.py --validate
#   python run.py --week
# THEN: rojo serve → Studio Connect → smoke → answer y/n on @human

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n | other @ = Ollama/Space Bunny

## QUALITY GATES
- `python run.py --validate` must stay OK
- Studio Output: `[Generator] map floor ready`, no Infinite yield Checkpoints, no Sound asset-type errors
- Play: Path floor, green CP, coins, void, pressure plate

---

## AGENT SPRINT Z — from zero (do these first)
- [ ] Z1 | REWRITE Generator from baseline seed: destroy Baseplate; Map.Path + SpawnPlaza + SpawnLocation; workspace.Checkpoints as Checkpoint..id; Coins; ADD 3 Obstacle Parts per section; print [Generator] map floor ready + section ids | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [ ] Z2 | REWRITE Effects.client.luau: pcall around Sound; never use broken ids (e.g. 203785492); keep CheckpointReached + CoinCollected flash tweens | @client_programmer | → src/client/Effects.client.luau
- [ ] Z3 | REWRITE LevelConfig: gaps 50,70,90,110,130 coins 5,5,5,5,8 | @content_author | → src/shared/Content/LevelConfig.luau
- [ ] Z4 | APPEND GDD #map-layout: path width 28, floor Y 5, obstacle size notes | @game_designer | → docs/GDD.md#map-layout
- [ ] Z5 | REWRITE QA_REPORT with ## BUGS ## SUGGESTIONS ## TEST CASES ## SCORE and "- overall: NN" | @qa_engineer | → docs/QA_REPORT.md
- [ ] Z6 | Fix HIGH/CRIT from Z5 only; if only LOW — NOTE no FILE | @refactorer
- [ ] Z7 | NOTE-only: confirm Remotes has CheckpointReached + CoinCollected getOrCreate | @integrator

## HUMAN GATES (after Z1–Z7)
- [ ] H1 | Studio: Map Path visible (not bare Baseplate); Output has [Generator] map floor ready | @human
- [ ] H2 | Studio: touch CP + pick coin; HUD updates; no Infinite yield / Sound type errors | @human
- [ ] H3 | Studio: stand on blue plate opens red gate; void respawn works | @human
- [ ] H4 | Human final accept | @human

## BOOTSTRAP (do not delete)
- Remotes getOrCreate, InitRemotes, PlayerData Studio-offline
- Checkpoints creates folder if missing
- Coins / Void / Puzzles / HUD / Generator seed map
