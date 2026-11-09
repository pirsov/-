# LAST_UPDATE: FIX from smoke — game1
# Auto from smoke N/Другое. Keep src. Activate project first if src empty.
#   python -u run.py --week --sleep 0

## SMOKE ISSUES
- q4: [other] Spawn — загрузка при спавне доходит до минуты
- q7: [n] Best в HUD?

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n

## DONE (keep)
- [x] prior weeks / smoke captured | @integrator

## AGENT F — fixes from smoke
- [ ] F1 | REWRITE Generator lighter map; Instance.new("SpawnLocation") real class; Path+CP+Coins; no Baseplate; join under ~10s | @gameplay_programmer | -> src/server/Level/Generator.server.luau
- [ ] F2 | REWRITE PlayerData init attrs immediately on join; no blocking DataStore in Studio | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [ ] F3 | REWRITE InitRemotes getOrCreate remotes fast; no long WaitForChild loops | @gameplay_programmer | -> src/server/InitRemotes.server.luau
- [ ] F4 | REWRITE PlayerData BestTime=0 init; on leave/finish set BestTime from RunStartedAt if better; Studio only no DataStore | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [ ] F5 | REWRITE Checkpoints set RunStartedAt if nil; update BestTime on last CP; attrs only on Player; NEVER Remotes.CoinsCollected | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
- [ ] F6 | REWRITE HUD Best via player:GetAttribute BestTime; show -- only if nil/0; NEVER character:GetAttribute | @client_programmer | -> src/client/HUD.client.luau

## HUMAN GATES
- [ ] H11 | Studio: re-check failed smoke items (Best + spawn load) | @human
- [ ] H12 | Final: python -u run.py --eval | @human
