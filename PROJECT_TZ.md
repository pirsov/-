# LAST_UPDATE: SMOKE — всё ок кроме Best: -- (BestTime никогда не пишется)
# Keep src. После smoke: week на B*.
#   python -u run.py --week --sleep 0
# AFTER: python -u run.py --eval

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n

## DONE (keep)
- [x] G* greenfield | @integrator
- [x] F* studio-fix | @gameplay_programmer
- [x] P1-P10 polish | @gameplay_programmer
- [x] R1-R5 repair HUD/CP/Coins/Generator/PlayerData | @gameplay_programmer
- [x] T* horror week | @gameplay_programmer
- [x] H1-H4 | @human

## AGENT B — BestTime (smoke: Best shows --)
- [ ] B1 | REWRITE PlayerData: init BestTime=0 if nil (not math.huge); on PlayerRemoving compute elapsed from RunStartedAt attr; if BestTime==0 or elapsed<BestTime then SetAttribute BestTime=elapsed; Studio only no DataStore | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [ ] B2 | REWRITE Checkpoints: on new Checkpoint also set RunStartedAt=os.clock if nil; when Checkpoint reaches last (or Score milestone) update BestTime if better; attrs only on Player | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
- [ ] B3 | REWRITE HUD: Best via player:GetAttribute("BestTime"); show Best: -- only if nil or 0; else Best: %.1f; NEVER character attrs | @client_programmer | -> src/client/HUD.client.luau

## HUMAN GATES
- [ ] H9 | Studio: Best shows number after leave/rejoin or finish CP; not -- | @human
- [ ] H10 | Final: python -u run.py --eval | @human
