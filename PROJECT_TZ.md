# LAST_UPDATE: Cycle 4 closed I011+I012 (cloud_fallback). E2E H11 PASS. Q1=B Q2=B.
# Held proposed: I009 sound, I010 CP VFX, I013 fog. Next: cycle 5 pulse or Desktop --week.

## DONE
- [x] F1-F5 | checkpoints/coins/playerdata/generator/hud | @integrator
- [x] H11 | Studio E2E smoke PASS | @human
- [x] I011 | Finish-line BestTime on last CP + leave | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
- [x] I012 | Death resets RunStartedAt + HUD Time only | @client_programmer | -> src/client/HUD.client.luau

## HELD (proposed)
- [ ] I009 | Coin pickup sound | @client_programmer
- [ ] I010 | Checkpoint VFX pulse | @client_programmer
- [ ] I013 | Horror fog preset | @gameplay_programmer

## NEXT
- [ ] H12 | python -u run.py --eval after Desktop pull | @human
