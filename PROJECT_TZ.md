# LAST_UPDATE: REPAIR R — left HUD dead (reads Character attrs); Checkpoints invents CoinsCollected; Spawn is Part
# Keep src. Answer n at H5 if still open, pull TZ, then week.
#   python -u run.py --week --sleep 0
# AFTER: python -u run.py --eval

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n

## DONE (keep)
- [x] G* greenfield | @integrator
- [x] F* studio-fix | @gameplay_programmer
- [x] P1-P10 polish visuals | @gameplay_programmer
- [x] H1-H4 | @human

## AGENT R — functional repair (agent writes Luau; Cursor only forge)
- [ ] R1 | REWRITE HUD: ScreenGui LEFT labels Time/CP/Coins/Best; EVERY frame player:GetAttribute Coins+Checkpoint (NEVER character:GetAttribute); remotes only trigger paint; CharacterAdded must NOT zero coins | @client_programmer | -> src/client/HUD.client.luau
- [ ] R2 | REWRITE Checkpoints: Touched SetAttribute Checkpoint+Score on Player; FireClient CheckpointReached only; CanTouch true; teleport+Died; NEVER Remotes.CoinsCollected; NEVER destroy Coins folder parts | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
- [ ] R3 | REWRITE Coins: CanTouch; coin:Destroy; plr:SetAttribute Coins; FireClient CoinCollected; FireAllClients UpdateLeaderboard name:coins | @gameplay_programmer | -> src/server/Gameplay/Coins.server.luau
- [ ] R4 | REWRITE Generator: destroy Baseplate; Instance.new("SpawnLocation") real class; green Neon CP; gold coins; Path grey; obstacles Y~6 on Path | @gameplay_programmer | -> src/server/Level/Generator.server.luau
- [ ] R5 | REWRITE PlayerData: init Player attrs Score/Checkpoint/Coins/BestTime if nil; CharacterAdded must not wipe Coins; Studio only no DataStore GetAsync | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau

## HUMAN GATES
- [ ] H5 | Studio: left HUD Time/CP/Coins tick; green CP + gold coins; real SpawnLocation | @human
- [ ] H6 | Studio: walk CP updates left CP; pickup coin updates left Coins AND right leaderboard | @human
- [ ] H7 | Studio: plate/gate + void; no Output errors CoinsCollected | @human
- [ ] H8 | Final: python -u run.py --eval | @human
