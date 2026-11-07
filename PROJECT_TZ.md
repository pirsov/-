# LAST_UPDATE: 2026-11-07 (agent sprint reopened — LLM writes game)
# FORGE: Cursor maintains forge only. Game code/docs = run.py --week + model.
# RUN:  $env:FORGE_BACKEND='ollama'       # local (or openrouter / spacebunny)
#       python run.py --doctor
#       python run.py --week
# YOU: Studio smoke only on @human; answer y/n when asked.

## LEGEND
- [ ] pending | [x] done | @human = you in Studio | other @ = LLM agent

## QUALITY GATES
- `python run.py --validate` must stay OK after agent FILE writes
- Studio: walkable floor, CP, coins, void, plate, no red Output (fix sounds if red)

---

## AGENT SPRINT A — LLM must do these (do not hand-write)
- [ ] A1 | REWRITE Generator from baseline: KEEP Path+SpawnPlaza+SpawnLocation+Checkpoint..id; ADD 3 Obstacle Parts per section between CPs; keep print section ids | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [ ] A2 | REWRITE Effects.client.luau: replace broken sound ids with working rbxassetid OR silent pcall; keep flash tweens | @client_programmer | → src/client/Effects.client.luau
- [ ] A3 | APPEND GDD #map-layout: studs for path width, floor Y, obstacle sizes from A1 | @game_designer | → docs/GDD.md#map-layout
- [ ] A4 | REWRITE LevelConfig: coins 5,5,5,5,8 and gaps 50,70,90,110,130 | @content_author | → src/shared/Content/LevelConfig.luau
- [ ] A5 | REWRITE QA_REPORT.md with headings ## BUGS ## SUGGESTIONS ## TEST CASES ## SCORE; under SCORE put "- overall: 86" | @qa_engineer | → docs/QA_REPORT.md
- [ ] A6 | Fix HIGH/CRIT from A5 only; if only LOW — NOTE no FILE | @refactorer

## HUMAN GATES (after agent sprint — Studio y/n)
- [ ] W1.5 | Studio smoke baseline (floor, CP, coin, void, plate) | @human
- [ ] W2.4 | Studio: coins appear between checkpoints | @human
- [ ] W3.4 | Studio: coin/CP feedback without red sound errors | @human
- [ ] W4.3 | Studio: stand on plate opens gate | @human
- [ ] W6.4 | Studio full smoke 10 min | @human
- [ ] W7.4 | Human final accept / ship | @human

## BOOTSTRAP SEEDS (already in src — agent improves, does not delete)
- Remotes getOrCreate + CoinCollected
- InitRemotes require Remotes
- PlayerData Studio offline (no GetDataStore in Studio)
- Checkpoints Touched + LoadCharacter
- Coins + Void + Puzzles pressure plate
- Generator Map/Path + Spawn (agent A1 extends with obstacles)
- HUD / Effects / Leaderboard stubs

## CLOSED HISTORICAL (do not reopen)
- [x] W0.1 | Seeds shipped | @human
- [x] W0.2 | Historical MVP | @human
