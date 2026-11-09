# LAST_UPDATE: FIX from smoke — game1
# Auto from smoke N/Другое. Keep src. Run: python -u run.py --week --sleep 0

## SMOKE ISSUES
- q4: [other] Spawn — загрузка при спавне доходит до минуты
- q7: [n] Best в HUD?

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n

## DONE (keep)
- [x] prior weeks / smoke captured | @integrator

## AGENT F — fixes from smoke
- [ ] F1a | REWRITE Generator: lighter map build; fewer Parts; defer non-critical Instance.new; Path+SpawnLocation+CP+Coins only; no Baseplate | @gameplay_programmer | -> src/server/Level/Generator.server.luau
- [ ] F1b | REWRITE PlayerData/InitRemotes: no blocking waits on join; SetAttribute defaults immediately | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [ ] F1c | REWRITE InitRemotes getOrCreate remotes fast; no long WaitForChild loops | @gameplay_programmer | -> src/server/InitRemotes.server.luau
- [ ] F2a | REWRITE PlayerData BestTime=0 init; on leave/finish set BestTime from RunStartedAt if better; Studio only | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [ ] F2b | REWRITE Checkpoints set RunStartedAt; update BestTime on last CP; attrs on Player | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
- [ ] F2c | REWRITE HUD Best from player:GetAttribute BestTime; -- only if nil/0 | @client_programmer | -> src/client/HUD.client.luau

## HUMAN GATES
- [ ] HF1 | Studio: re-check failed smoke items | @human
- [ ] HF2 | Final: python -u run.py --eval | @human
