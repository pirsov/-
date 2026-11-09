# LAST_UPDATE: FIX after T* partial — Checkpoints still has CoinsCollected; Best + spawn
# Marked old T* done. Pending F* only. Soft gate continues on INVALID.
#   python -u run.py --project game1
#   $env:FORGE_BACKEND='ollama'; python -u run.py --week --sleep 0

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n

## DONE (keep)
- [x] T1-T5 client/Generator pass | @client_programmer
- [x] prior horror / polish | @integrator

## AGENT F — must fix Checkpoints FIRST (gate fail)
- [ ] F1 | REWRITE Checkpoints: Touched SetAttribute Checkpoint+Score on Player; FireClient CheckpointReached only; CanTouch true; teleport+Died; NEVER Remotes.CoinsCollected; NEVER destroy Coins folder parts; set RunStartedAt if nil; update BestTime on last CP | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
- [ ] F2 | REWRITE Coins: CanTouch; coin:Destroy; plr:SetAttribute Coins; FireClient CoinCollected; FireAllClients UpdateLeaderboard | @gameplay_programmer | -> src/server/Gameplay/Coins.server.luau
- [ ] F3 | REWRITE PlayerData BestTime=0 init not math.huge; on PlayerRemoving BestTime from RunStartedAt if better; attrs on Player; Studio only | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [ ] F4 | REWRITE Generator lighter map; Instance.new("SpawnLocation") real class; Path Checkpoints Coins folders; destroy Baseplate; join under ~10s | @gameplay_programmer | -> src/server/Level/Generator.server.luau
- [ ] F5 | REWRITE HUD Best+Coins+Checkpoint via player:GetAttribute only; Best -- only if nil/0; NEVER character:GetAttribute | @client_programmer | -> src/client/HUD.client.luau

## HUMAN GATES
- [ ] H11 | Studio: no CoinsCollected errors; Best number; spawn not ~1min | @human
- [ ] H12 | Final: python -u run.py --eval | @human
