# LAST_UPDATE: Cycle 3 E2E pulse — open_questions Q1-Q2 issued; awaiting human answers. No code.
#   git pull; python -u run.py --project game1; python -u run.py --eval

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n

## DONE
- [x] T* prior | @integrator
- [x] F1 | Checkpoints no CoinsCollected | @gameplay_programmer | -> src/server/Gameplay/Checkpoints.server.luau
- [x] F2 | Coins whitelist remotes | @gameplay_programmer | -> src/server/Gameplay/Coins.server.luau
- [x] F3 | PlayerData BestTime float 0; set_best_time if new<current; RunStartedAt on leave | @gameplay_programmer | -> src/server/Data/PlayerData.server.luau
- [x] F4 | Generator SpawnLocation + light map + 60s async spawn poll | @gameplay_programmer | -> src/server/Level/Generator.server.luau
- [x] F5 | HUD Best -- if nil/0; player:GetAttribute only | @client_programmer | -> src/client/HUD.client.luau

## CYCLE 3 — human / pulse
- [ ] H11 | Studio smoke: Best float after leave/rejoin; spawn ready; no CoinsCollected | @human
- [ ] H12 | Final: python -u run.py --eval | @human
- [ ] E2E | promote compact + open_questions pack | @human
