# LAST_UPDATE: 2026-11-08 GREENFIELD — src/ wiped; agent creates game from zero
# FORGE: LLM writes ALL of src/. Cursor = forge only.
# RUN:
#   $env:FORGE_BACKEND = "ollama"
#   Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue
#   .\scripts\reset-week.ps1
#   python run.py --doctor
#   python run.py --week
# THEN: rojo serve → Studio Connect → H* y/n

## LEGEND
- [ ] pending | [x] done | @human = Studio | other @ = LLM CREATE/REWRITE

## GATES
- After each FILE: forge validators (no PlayerRespawn, no top-level return on Scripts)
- Studio: map Path, CP, coins, plate, void; no Infinite yield / bad SoundId

---

## AGENT GREENFIELD G — create everything
- [ ] G1 | CREATE Remotes ModuleScript: Folder Remotes under ReplicatedStorage; getOrCreate Checkpoint, CheckpointReached, UpdateLeaderboard, CoinCollected; return table (never return Folder) | @integrator | → src/shared/Gameplay/Remotes.luau
- [ ] G2 | CREATE InitRemotes.server.luau: require Gameplay.Remotes and print ready | @gameplay_programmer | → src/server/InitRemotes.server.luau
- [ ] G3 | CREATE LevelConfig ModuleScript return { sections = { id,gap,coins }x5 } gaps 50,70,90,110,130 coins 5,5,5,5,8 | @content_author | → src/shared/Content/LevelConfig.luau
- [ ] G4 | CREATE Generator.server.luau: destroy Baseplate; Map.Path+SpawnPlaza+SpawnLocation; workspace.Checkpoints Checkpoint..id; Coins; 3 Obstacles/section; print [Generator] map floor ready | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [ ] G5 | CREATE Checkpoints.server.luau: ensure Checkpoints folder; Touched SetAttribute Checkpoint idx; FireClient CheckpointReached; Died LoadCharacter teleport to Checkpoint..idx | @gameplay_programmer | → src/server/Gameplay/Checkpoints.server.luau
- [ ] G6 | CREATE Coins.server.luau: hook workspace.Coins parts; award Coins attr; FireClient CoinCollected | @gameplay_programmer | → src/server/Gameplay/Coins.server.luau
- [ ] G7 | CREATE Void.server.luau: if HRP.Y < -20 then LoadCharacter | @gameplay_programmer | → src/server/Gameplay/Void.server.luau
- [ ] G8 | CREATE Puzzles.server.luau: PressurePlate + Gate; stand opens gate | @gameplay_programmer | → src/server/Gameplay/Puzzles.server.luau
- [ ] G9 | CREATE PlayerData.server.luau: Studio offline attrs Score/Checkpoint/Coins/BestTime; no GetDataStore in Studio | @gameplay_programmer | → src/server/Data/PlayerData.server.luau
- [ ] G10 | CREATE HUD.client.luau: Time CP Coins Best labels; listen CheckpointReached + CoinCollected | @client_programmer | → src/client/HUD.client.luau
- [ ] G11 | CREATE Effects.client.luau: flash tweens; Sound in pcall only with valid ids | @client_programmer | → src/client/Effects.client.luau
- [ ] G12 | CREATE Leaderboard.client.luau stub UI "Leaderboard (waiting...)" | @client_programmer | → src/client/Leaderboard.client.luau
- [ ] G13 | APPEND GDD #greenfield-layout studs for Path/CP/plate | @game_designer | → docs/GDD.md#greenfield-layout
- [ ] G14 | REWRITE QA_REPORT ## BUGS ## SUGGESTIONS ## TEST CASES ## SCORE overall number | @qa_engineer | → docs/QA_REPORT.md
- [ ] G15 | Fix HIGH/CRIT from G14 only; if only LOW — NOTE no FILE | @refactorer

## HUMAN GATES
- [ ] H1 | Studio: [Generator] map floor ready; walkable Path; green CPs | @human
- [ ] H2 | Studio: coin + CP HUD; no Infinite yield; no Sound type errors | @human
- [ ] H3 | Studio: plate opens gate; void respawns | @human
- [ ] H4 | Final accept | @human

## NOTE
`src/` starts EMPTY (only folders). Do not invent PlayerRespawn. Scripts: no top-level return. Modules: end with return {…}.
