# LAST_UPDATE: 2026-11-10 07:02:14
# Q1 answered: BestTime = float seconds; set only if new < current; NOT tied to Last CP alone
# Q2 answered: join poll budget 60s async OK
# Cursor does NOT write Luau. Run on machine with Ollama:
#   $env:FORGE_BACKEND='ollama'; python -u run.py --week --sleep 0 --max 2 --hitl y

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n

## DONE (keep)
- [x] T* / prior weeks | @integrator
- [x] inventory state.json cycle0 | @human

## AGENT F — cycle 1 batch (ONE system first: Checkpoints)
- [x] F1 | REWRITE Checkpoints: Touched SetAttribute Checkpoint+Score on Player; FireClient CheckpointReached only; CanTouch true; teleport+Died; set RunStartedAt=os.clock if nil; NEVER Remotes.CoinsCollected; NEVER destroy Coins folder; attrs only on Player | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
  - DONE 2026-11-10 07:02:08 | validator PASS on activated game1 snapshot (no CoinsCollected); Ollama unavailable on cloud VM — Windows can re-run --week F1 if live src still dirty
- [x] F2 | REWRITE Coins: CanTouch; coin:Destroy; plr:SetAttribute Coins; FireClient CoinCollected; FireAllClients UpdateLeaderboard name:coins | @gameplay_programmer | -> src/server/Gameplay/Coins.server.luau
  - DONE 2026-11-10 07:02:14 | validator PASS Coins whitelist remotes after activate

## QUEUED (cycle 2 — do not start until F1+F2 closed)
- [ ] F3 | REWRITE PlayerData: BestTime float seconds init 0; helpers set_best_time only if new>0 and (BestTime==0 or new<BestTime); get via GetAttribute; on PlayerRemoving elapsed=os.clock-RunStartedAt then set_best_time; Studio only | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [ ] F4 | REWRITE Generator lighter map; Instance.new("SpawnLocation"); Path Checkpoints Coins; destroy Baseplate; join poll budget 60s async no hang | @gameplay_programmer | -> src/server/Level/Generator.server.luau
- [ ] F5 | REWRITE HUD Best+Coins+Checkpoint via player:GetAttribute; Best -- only if nil/0 else %.1f; NEVER character:GetAttribute | @client_programmer | -> src/client/HUD.client.luau

## HUMAN GATES
- [ ] H11 | Studio smoke: no CoinsCollected; Best float; spawn poll OK | @human
