# LAST_UPDATE: 2026-11-07 06:30:00
# NEXT_AGENT: @qa_engineer
# FORGE: Quality Forge week-long pipeline — resume anytime; first `- [ ]` wins
# RUN: python run.py --loop --max 500
#       python run.py --score
#       python run.py --validate

## LEGEND
- [ ] — pending
- [x] — done
- [-] — blocked (see NOTE below the task)
- @human — needs human action, agents do not touch

## QUALITY GATES
- Gate A (after SYSTEMS): `python run.py --validate` must exit 0
- Gate B (after CRITIQUE): QA SCORE ≥ 80 in docs/QA_REPORT.md
- Gate C (after HARDEN): human Studio smoke test

---

## PHASE 1 — CONCEPT  (BLUEPRINT)
- [x] P1.1 | Define genre + core loop (3-5 bullet points, concrete) | @game_designer | → docs/GDD.md#core-loop
- [x] P1.2 | Define win/lose conditions + scoring | @game_designer | → docs/GDD.md#win-lose
- [x] P1.3 | List MVP features (5-10, each 1 line) | @game_designer | → docs/GDD.md#mvp
- [x] P1.4 | Human review of GDD | @human

## PHASE 2 — ARCHITECTURE  (BLUEPRINT)
- [x] P2.1 | Create Rojo folder tree + default.project.json | @tech_architect | → src/ + default.project.json
- [x] P2.2 | List required scripts (file path + single responsibility) | @tech_architect | → docs/ARCHITECTURE.md
- [x] P2.3 | Define RemoteEvents contract (name → payload) | @tech_architect | → docs/ARCHITECTURE.md#remotes

## PHASE 3–7 — MVP SYSTEMS (completed; sources repaired 2026-11-07 after APPEND overwrite bug)
- [x] P3.1 | Server: player data (DataStore, pcall, autosave) | @gameplay_programmer | → src/server/Data/PlayerData.server.luau
- [x] P3.2 | Server: checkpoints + respawn | @gameplay_programmer | → src/server/Gameplay/Checkpoints.server.luau
- [x] P3.3 | Shared: leaderboard remotes module | @gameplay_programmer | → src/shared/Gameplay/Remotes.luau
- [x] P3.4 | Client: HUD (timer, checkpoint count) | @client_programmer | → src/client/HUD.client.luau
- [x] P3.5 | Client: sound + UI polish | @client_programmer | → src/client/Effects.client.luau
- [x] P4.1 | Level generator script (10 checkpoints, increasing gap) | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [x] P4.2 | Human playtest in Studio | @human
- [x] P5.1 | Static review of all .luau files, produce report | @qa_engineer | → docs/QA_REPORT.md
- [x] P5.2 | Fix HIGH/CRIT bugs from QA_REPORT | @refactorer | (edits existing files)
- [x] P6.1 | Write docs/RELEASE.md with rojo build command + publish checklist | @builder | → docs/RELEASE.md
- [x] P20.1-P20.19 | Micro rebuild (historical; corrupted by APPEND overwrite — repaired) | @refactorer
- [x] P20.20 | Rewrite PlayerData.server.luau with task.wait autosave (no wait()) | @refactorer | → src/server/Data/PlayerData.server.luau
  - DONE 2026-11-07 06:30 | Repaired manually as part of orchestrator bugfix; uses task.wait(60)

---

## PHASE 30 — INTEGRITY GATE (after forge repair)
- [x] P30.1 | Static QA of repaired sources; write SCORE 0-100 | @qa_engineer | → docs/QA_REPORT.md
  - DONE 2026-11-07 | score 82; only LOW open
- [ ] P30.2 | If QA_REPORT has HIGH/CRIT: REWRITE those .luau files. If only LOW/RESOLVED: reply DONE with NOTE no code changes and NO <FILE> tags | @refactorer
- [ ] P30.3 | Integrator: verify Remotes names match HUD/Effects/Checkpoints. If already match, DONE with NOTE only (no FILE). If broken, REWRITE Remotes.luau as getOrCreate table | @integrator | → src/shared/Gameplay/Remotes.luau

## PHASE 31 — DEPTH BLUEPRINT (week-long quality)
- [ ] P31.1 | APPEND depth layers MVP/Plus/Deluxe with concrete numbers | @game_designer | → docs/GDD.md#depth-layers
- [ ] P31.2 | APPEND puzzle types + section layout (5 sections) | @game_designer | → docs/GDD.md#sections
- [ ] P31.3 | Write system specs for puzzles, coins, leaderboard | @systems_designer | → docs/SYSTEMS.md
- [ ] P31.4 | Extend ARCHITECTURE with new module paths for Plus features | @tech_architect | → docs/ARCHITECTURE.md#plus-modules

## PHASE 32 — PLUS SYSTEMS (one module per task)
- [ ] P32.1 | Create SCRIPT (not ModuleScript) Coins.server.luau: --!strict, no top-level return; on coin Part Touched award attribute Coins+=1 and Remotes.CoinCollected:FireClient; use require Gameplay.Remotes | @gameplay_programmer | → src/server/Gameplay/Coins.server.luau
- [ ] P32.2 | REWRITE full Remotes.luau (do not APPEND after return): keep getOrCreate + return table including CoinCollected | @gameplay_programmer | → src/shared/Gameplay/Remotes.luau
- [x] P32.3 | Create shared Content/LevelConfig.luau (gaps, coin counts per section) | @content_author | → src/shared/Content/LevelConfig.luau
  - DONE 2026-11-07 | LevelConfig with gaps 50..130 — verify locally; may need --!strict
- [ ] P32.4 | Rewrite Generator.server.luau: require LevelConfig from ReplicatedStorage.Content; spawn Checkpoint1..N and Coin parts; NO BreakJoints; NO require Checkpoints module; no markdown fences | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [ ] P32.5 | APPEND coin count label to HUD (APPEND only) | @client_programmer | → src/client/HUD.client.luau
- [ ] P32.6 | APPEND coin pickup sound in Effects (APPEND only) | @client_programmer | → src/client/Effects.client.luau
- [ ] P32.7 | Create simple pressure-plate puzzle server script | @gameplay_programmer | → src/server/Gameplay/Puzzles.server.luau
- [ ] P32.8 | PlayerData: persist coins + bestTime with pcall | @gameplay_programmer | → src/server/Data/PlayerData.server.luau

## PHASE 33 — CRITIQUE LOOP (repeatable quality)
- [ ] P33.1 | Full QA with SCORE; list CRIT/HIGH | @qa_engineer | → docs/QA_REPORT.md
- [ ] P33.2 | Fix HIGH/CRIT from P33.1 | @refactorer
- [ ] P33.3 | Re-QA; if SCORE < 80 note what remains | @qa_engineer | → docs/QA_REPORT.md
- [ ] P33.4 | Fix remaining HIGH/CRIT from P33.3 | @refactorer
- [ ] P33.5 | Final QA gate; SCORE must be documented | @qa_engineer | → docs/QA_REPORT.md

## PHASE 34 — POLISH
- [ ] P34.1 | APPEND juice notes (tween pulses, checkpoint flash) to GDD | @game_designer | → docs/GDD.md#juice
- [ ] P34.2 | Client: checkpoint flash tween on CheckpointReached | @client_programmer | → src/client/Effects.client.luau
- [ ] P34.3 | Server: kill brick void below Y=-20 teleports via checkpoint (no Health=0) | @gameplay_programmer | → src/server/Gameplay/Void.server.luau
- [ ] P34.4 | Builder: refresh RELEASE.md with Plus feature checklist | @builder | → docs/RELEASE.md

## PHASE 35 — HARDEN + HUMAN
- [ ] P35.1 | Integrator pass: cross-file remotes + attribute names | @integrator
- [ ] P8.1 | rojo build + open build/game.rbxlx in Studio, capture errors from Output | @human
- [ ] P6.2 | Human final check | @human

## BACKLOG — DEEPEN (orchestrator may unlock if week continues)
- [ ] P90.1 | Deluxe: moving platforms server script | @gameplay_programmer | → src/server/Level/MovingPlatforms.server.luau
- [ ] P90.2 | Deluxe: leaderboard UpdateLeaderboard top-10 UI | @client_programmer | → src/client/Leaderboard.client.luau
- [ ] P90.3 | Deluxe: 3 more sections in LevelConfig | @content_author | → src/shared/Content/LevelConfig.luau
- [ ] P90.4 | Deluxe: sequence puzzle type | @gameplay_programmer | → src/server/Gameplay/SequencePuzzle.server.luau
