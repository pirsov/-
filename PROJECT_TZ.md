# LAST_UPDATE: 2026-11-07 13:55:00
# FORGE: WEEK MODE — seed-first, 14b for code, no micro-split
# RUN:  python run.py --week
#       python run.py --loop --max 200 --sleep 30
#       python run.py --validate
# DAILY HUMAN: open Studio, smoke checkpoints+coins+plate, mark @human [x]

## LEGEND
- [ ] pending | [x] done | @human = you once/day (~10 min)

## QUALITY GATES
- After every 5 agent steps orchestrator runs validate (week mode)
- Gate Studio (@human): no red errors; CP touch; coin pickup; pressure plate
- Never rewrite Remotes/Checkpoints/Coins/Generator from scratch — APPEND or NOTE-only

---

## BASELINE (already shipped — do not reopen)
- [x] W0.1 | MVP Remotes+Checkpoints+HUD+Effects+PlayerData+LevelConfig+Coins+Generator+Void+Puzzles seeds | @human
- [x] W0.2 | Phase 1–7 historical MVP | @human

---

## DAY 1 — LOCK BASELINE (docs only + verify)
- [ ] W1.1 | APPEND week goals: concrete studs (gap 50/70/90/110/130, coin Y=7) | @game_designer | → docs/GDD.md#week-goals
- [ ] W1.2 | REWRITE docs/SYSTEMS.md short: remotes table + attributes Checkpoint/Coins/BestTime | @systems_designer | → docs/SYSTEMS.md
- [ ] W1.3 | Static QA SCORE; only open bugs; no PlayerRespawn as CRIT | @qa_engineer | → docs/QA_REPORT.md
- [ ] W1.4 | If only LOW: DONE NOTE no FILE. Else fix HIGH only | @refactorer
- [ ] W1.5 | Studio smoke baseline (CP, coin, void, plate) | @human

## DAY 2 — GENERATOR TUNE (tiny edits)
- [ ] W2.1 | APPEND one print after spawn listing section ids from LevelConfig | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [ ] W2.2 | LevelConfig: set coins per section to 5,5,5,5,8 (REWRITE full return table only) | @content_author | → src/shared/Content/LevelConfig.luau
- [ ] W2.3 | NOTE-only: confirm Remotes has CoinCollected; if missing REWRITE full Remotes getOrCreate table | @integrator | → src/shared/Gameplay/Remotes.luau
- [ ] W2.4 | Studio: coins appear between checkpoints | @human

## DAY 3 — HUD / FX POLISH (APPEND only)
- [ ] W3.1 | APPEND: when CoinCollected fires, flash CoinCount BackgroundTransparency 0.1→0.5 via TweenService | @client_programmer | → src/client/Effects.client.luau
- [ ] W3.2 | APPEND: show BestTime attribute under coins if present | @client_programmer | → src/client/HUD.client.luau
- [ ] W3.3 | QA SCORE after client polish | @qa_engineer | → docs/QA_REPORT.md
- [ ] W3.4 | Studio: coin sound + HUD coins update | @human

## DAY 4 — PUZZLE HARDENING
- [ ] W4.1 | APPEND debounce: ignore TouchEnded spam; standing counter never negative (already mostly done — only if broken REWRITE full Puzzles.server.luau seed-style) | @gameplay_programmer | → src/server/Gameplay/Puzzles.server.luau
- [ ] W4.2 | APPEND GDD section: PressurePlate at (12,5,-30), Gate at (12,11,-40) | @game_designer | → docs/GDD.md#puzzle-layout
- [ ] W4.3 | Studio: stand on plate opens gate | @human

## DAY 5 — DATA + SCORING
- [ ] W5.1 | APPEND on PlayerRemoving: if timer exists set BestTime when better (read attribute TimeAlive or skip if missing) | @gameplay_programmer | → src/server/Data/PlayerData.server.luau
- [ ] W5.2 | APPEND SYSTEMS: BestTime persistence notes | @systems_designer | → docs/SYSTEMS.md
- [ ] W5.3 | QA SCORE | @qa_engineer | → docs/QA_REPORT.md
- [ ] W5.4 | Fix HIGH/CRIT only; else NOTE no FILE | @refactorer

## DAY 6 — POLISH PASS
- [ ] W6.1 | APPEND juice: checkpoint flash already in Effects — document only | @game_designer | → docs/GDD.md#juice
- [ ] W6.2 | Builder: RELEASE checklist includes coins+plate+void | @builder | → docs/RELEASE.md
- [ ] W6.3 | Integrator NOTE-only cross-check remotes names | @integrator
- [ ] W6.4 | Studio full smoke 10 min | @human

## DAY 7 — CRITIQUE + FREEZE
- [ ] W7.1 | Full QA with SCORE; list only real open bugs | @qa_engineer | → docs/QA_REPORT.md
- [ ] W7.2 | Fix HIGH/CRIT only | @refactorer
- [ ] W7.3 | Re-QA SCORE must be documented ≥ 80 or explain | @qa_engineer | → docs/QA_REPORT.md
- [ ] W7.4 | Human final accept / ship | @human

## BACKLOG (only if Day 7 finishes early — still seed-sized)
- [ ] W9.1 | Create MovingPlatforms.server.luau: one Part tween Z -20↔-80 loop Anchored | @gameplay_programmer | → src/server/Level/MovingPlatforms.server.luau
- [ ] W9.2 | Leaderboard.client.luau: listen UpdateLeaderboard stub TextLabel | @client_programmer | → src/client/Leaderboard.client.luau
