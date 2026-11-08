# LAST_UPDATE: 2026-11-08 FIX after greenfield — agent repairs playable map
# RUN: $env:FORGE_BACKEND='ollama'; python run.py --week

## LEGEND
- [ ] pending | [x] done

## DONE GREENFIELD (keep [x] on your machine if already done)
- [x] G1 | Remotes | @integrator
- [x] G2 | InitRemotes | @gameplay_programmer
- [x] G3 | LevelConfig | @content_author
- [x] G4 | Generator (needs FIX F1) | @gameplay_programmer
- [x] G5 | Checkpoints | @gameplay_programmer
- [x] G6 | Coins (needs FIX F2) | @gameplay_programmer
- [x] G7 | Void (needs FIX F3) | @gameplay_programmer
- [x] G8 | Puzzles (needs FIX F4) | @gameplay_programmer
- [x] G9 | PlayerData | @gameplay_programmer
- [x] G10 | HUD | @client_programmer

## AGENT FIX F — make Studio playable (LLM REWRITE)
- [ ] F1 | REWRITE Generator: MUST Instance.new Map+Path+SpawnPlaza+SpawnLocation (never WaitForChild Map first); ensureFolder Checkpoints/Coins; destroy Baseplate; Checkpoint..id; coins; 3 obstacles/section; print [Generator] map floor ready | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [ ] F2 | REWRITE Coins: require ReplicatedStorage.Gameplay.Remotes only (no .shared.); hook existing + ChildAdded; destroy the coin Part not hit limb | @gameplay_programmer | → src/server/Gameplay/Coins.server.luau
- [ ] F3 | REWRITE Void: Heartbeat/watch HRP.Position.Y < -20 then LoadCharacter (not Touched-on-HRP) | @gameplay_programmer | → src/server/Gameplay/Void.server.luau
- [ ] F4 | REWRITE Puzzles: create PressurePlate+Gate if missing; Touched open; TouchEnded close (never .Left); require Gameplay.Remotes if needed | @gameplay_programmer | → src/server/Gameplay/Puzzles.server.luau
- [ ] F5 | CREATE/REWRITE Effects.client.luau: GetService Players; pcall sounds; flash tweens | @client_programmer | → src/client/Effects.client.luau
- [ ] F6 | CREATE Leaderboard.client.luau stub | @client_programmer | → src/client/Leaderboard.client.luau
- [ ] F7 | QA ## BUGS ## SUGGESTIONS ## TEST CASES ## SCORE | @qa_engineer | → docs/QA_REPORT.md
- [ ] F8 | Fix HIGH/CRIT only; else NOTE | @refactorer

## HUMAN
- [ ] H1 | Studio: Path+CPs; [Generator] map floor ready | @human
- [ ] H2 | Studio: coins+CP HUD; no Infinite yield | @human
- [ ] H3 | Studio: plate/gate + void | @human
- [ ] H4 | Final accept | @human
