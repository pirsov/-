# LAST_UPDATE: POLISH sprint after ship-ready skeleton (floor+coins+HUD work)
# Keep src. Pull TZ then: python -u run.py --week --sleep 0
# AFTER: python -u run.py --eval

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n

## DONE — greenfield + studio-fix (do not recreate)
- [x] G1-G15 | greenfield create | @integrator
- [x] F1 | LevelConfig Luau array | @gameplay_programmer | -> src/shared/Content/LevelConfig.luau
- [x] F2 | Coins coin:Destroy + FindFirstChild | @gameplay_programmer | -> src/server/Gameplay/Coins.server.luau
- [x] F3 | HUD ScreenGui | @client_programmer | -> src/client/HUD.client.luau
- [x] F4 | Leaderboard stub GUI | @client_programmer | -> src/client/Leaderboard.client.luau
- [x] F5 | Effects sounds | @client_programmer | -> src/client/Effects.client.luau
- [x] H1 | Studio map floor | @human
- [x] H2 | Studio coin+HUD | @human
- [x] H3 | Studio plate/void | @human
- [x] H4 | eval accept | @human

## AGENT P — polish playable loop (REWRITE existing; agent writes Luau)
- [ ] P1 | REWRITE Generator: destroy Baseplate; real Instance.new("SpawnLocation") under Map (not Part named Spawn); Path BrickColor Medium stone grey; Checkpoint parts Color green Neon Material; Coin parts Color gold/yellow; print [Generator] map floor ready | @gameplay_programmer | -> src/server/Level/Generator.server.luau
- [ ] P2 | REWRITE Checkpoints: on reach SetAttribute Checkpoint+Coins unchanged; also SetAttribute Score = Checkpoint*100; FireClient CheckpointReached; keep Died LoadCharacter teleport | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
- [ ] P3 | REWRITE Coins: after coin:Destroy FireClient; also plr:SetAttribute("Coins",(plr:GetAttribute("Coins") or 0)+1); FireAllClients UpdateLeaderboard with simple string of name+coins | @gameplay_programmer | -> src/server/Gameplay/Coins.server.luau
- [ ] P4 | REWRITE Puzzles: ensureFolder workspace.Puzzles once (no duplicate Folder each run); place PressurePlate ON Path at Z~40 Y~5.5 CanCollide true; Gate blocks Path; Touched open TouchEnded close; NEVER .Left | @gameplay_programmer | -> src/server/Gameplay/Puzzles.server.luau
- [ ] P5 | REWRITE Void: Heartbeat HRP.Y < -20 LoadCharacter only; no Touched void | @gameplay_programmer | -> src/server/Gameplay/Void.server.luau
- [ ] P6 | REWRITE PlayerData: Studio attrs only (no GetAsync DataStore); on PlayerAdded init Score/Checkpoint/Coins/BestTime if nil; on CharacterAdded do not wipe Coins | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [ ] P7 | REWRITE HUD: labels Time CP Coins Best; poll GetAttribute Coins/Checkpoint each RenderStepped OR AttributeChanged; keep remotes; player.CharacterAdded | @client_programmer | -> src/client/HUD.client.luau
- [ ] P8 | REWRITE Leaderboard: ScreenGui label; UpdateLeaderboard.OnClientEvent sets Text; show "Leaderboard (waiting...)" until first event | @client_programmer | -> src/client/Leaderboard.client.luau
- [ ] P9 | APPEND GDD #polish-loop notes: spawn Y, CP green, coin gold, plate Z | @game_designer | -> docs/GDD.md#polish-loop
- [ ] P10 | REWRITE QA_REPORT ## BUGS ## SUGGESTIONS ## TEST CASES ## SCORE overall NN from current src only | @qa_engineer | -> docs/QA_REPORT.md

## HUMAN GATES (after P*)
- [ ] H5 | Studio: green CPs + gold coins + real SpawnLocation; no Baseplate | @human
- [ ] H6 | Studio: plate opens gate on Path; void fall respawns; HUD attrs update | @human
- [ ] H7 | Studio: leaderboard text updates after coin; no Infinite yield | @human
- [ ] H8 | Final accept then: python -u run.py --eval | @human
