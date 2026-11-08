# LAST_UPDATE: FULL GREENFIELD RUN — src empty; agent builds game end-to-end
# AFTER RUN: python run.py --eval  →  docs/AGENT_RUN_REPORT.md
#
#   $env:FORGE_BACKEND="ollama"; $env:OLLAMA_NUM_PARALLEL="1"
#   Remove-Item Env:OPENROUTER_API_KEY -EA SilentlyContinue
#   Get-ChildItem src -Recurse -Filter *.luau | Remove-Item -Force
#   python run.py --doctor
#   python run.py --week
#   python run.py --eval

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n

## AGENT G — CREATE from zero (hardened rules)
- [ ] G1 | CREATE Remotes: Folder under RS named Remotes; getOrCreate Checkpoint,CheckpointReached,UpdateLeaderboard,CoinCollected; local Remotes={...}; return Remotes (never return Folder) | @integrator | → src/shared/Gameplay/Remotes.luau
- [ ] G2 | CREATE InitRemotes.server.luau: require Gameplay.Remotes; print [InitRemotes] ready | @gameplay_programmer | → src/server/InitRemotes.server.luau
- [ ] G3 | CREATE LevelConfig return {sections={{id,gap,coins}x5}} gaps 50,70,90,110,130 coins 5,5,5,5,8 | @content_author | → src/shared/Content/LevelConfig.luau
- [ ] G4 | CREATE Generator: Instance.new Map+Path+SpawnPlaza+SpawnLocation (NO WaitForChild Map first); ensureFolder Checkpoints+Coins; destroy Baseplate; Checkpoint..id; coins; 3 obstacles/section; print [Generator] map floor ready | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [ ] G5 | CREATE Checkpoints.server: ensure folder; Touched; SetAttribute Checkpoint numeric idx; FireClient CheckpointReached; Died LoadCharacter; teleport Checkpoint..idx; NO top-level return | @gameplay_programmer | → src/server/Gameplay/Checkpoints.server.luau
- [ ] G6 | CREATE Coins.server: require Gameplay.Remotes only; ChildAdded+existing; Destroy coin Part not hit; FireClient CoinCollected | @gameplay_programmer | → src/server/Gameplay/Coins.server.luau
- [ ] G7 | CREATE Void.server: Heartbeat if HRP.Y<-20 LoadCharacter (not Touched-on-HRP) | @gameplay_programmer | → src/server/Gameplay/Void.server.luau
- [ ] G8 | CREATE Puzzles.server: create PressurePlate+Gate; Touched open; TouchEnded close (never .Left) | @gameplay_programmer | → src/server/Gameplay/Puzzles.server.luau
- [ ] G9 | CREATE PlayerData.server: Studio offline attrs Score/Checkpoint/Coins/BestTime; no GetDataStore in Studio | @gameplay_programmer | → src/server/Data/PlayerData.server.luau
- [ ] G10 | CREATE HUD.client: Time CP Coins Best; listen CheckpointReached+CoinCollected | @client_programmer | → src/client/HUD.client.luau
- [ ] G11 | CREATE Effects.client: GetService Players; pcall Sound; flash tweens | @client_programmer | → src/client/Effects.client.luau
- [ ] G12 | CREATE Leaderboard.client stub text Leaderboard (waiting...) | @client_programmer | → src/client/Leaderboard.client.luau
- [ ] G13 | APPEND GDD #greenfield-layout Path width/floor Y/CP gaps | @game_designer | → docs/GDD.md#greenfield-layout
- [ ] G14 | REWRITE QA_REPORT ## BUGS ## SUGGESTIONS ## TEST CASES ## SCORE overall NN | @qa_engineer | → docs/QA_REPORT.md
- [ ] G15 | Fix HIGH/CRIT from G14 only; if only LOW — NOTE no FILE | @refactorer

## HUMAN GATES
- [ ] H1 | Studio: [Generator] map floor ready; Path+green CPs | @human
- [ ] H2 | Studio: coin+CP HUD; no Infinite yield; no bad SoundId | @human
- [ ] H3 | Studio: plate/gate + void respawn | @human
- [ ] H4 | Final accept then run: python run.py --eval | @human
