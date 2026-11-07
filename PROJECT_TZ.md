# LAST_UPDATE: 2026-11-07 14:00:00
# FORGE: WEEK MODE — agent days 1–7 code/docs closed; human Studio gates remain
# RUN:  python run.py --validate
#       python run.py --week   (will pause on first @human)
# YOU: mark each @human [x] after Studio smoke, then re-run --week

## LEGEND
- [ ] pending | [x] done | @human = you ~10 min in Studio

## QUALITY GATES
- `python run.py --validate` must stay OK
- Studio: CP, coins, void, pressure plate, no red Output

---

## BASELINE
- [x] W0.1 | Seeds shipped | @human
- [x] W0.2 | Historical MVP | @human

## DAY 1 — LOCK BASELINE
- [x] W1.1 | Week goals concrete studs in GDD | @game_designer | → docs/GDD.md#week-goals
- [x] W1.2 | SYSTEMS remotes + attributes | @systems_designer | → docs/SYSTEMS.md
- [x] W1.3 | QA SCORE 86, no false PlayerRespawn CRIT | @qa_engineer | → docs/QA_REPORT.md
- [x] W1.4 | Only LOW — no code changes | @refactorer
- [ ] W1.5 | Studio smoke baseline (CP, coin, void, plate) | @human

## DAY 2 — GENERATOR TUNE
- [x] W2.1 | Generator prints section ids | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [x] W2.2 | LevelConfig coins 5,5,5,5,8 | @content_author | → src/shared/Content/LevelConfig.luau
- [x] W2.3 | Remotes has CoinCollected (confirmed) | @integrator
- [ ] W2.4 | Studio: coins appear between checkpoints | @human

## DAY 3 — HUD / FX
- [x] W3.1 | CoinCount flash on CoinCollected | @client_programmer | → src/client/Effects.client.luau
- [x] W3.2 | BestTime label on HUD | @client_programmer | → src/client/HUD.client.luau
- [x] W3.3 | QA after client polish | @qa_engineer | → docs/QA_REPORT.md
- [ ] W3.4 | Studio: coin sound + HUD coins update | @human

## DAY 4 — PUZZLE
- [x] W4.1 | Plate debounce + non-negative standing | @gameplay_programmer | → src/server/Gameplay/Puzzles.server.luau
- [x] W4.2 | Puzzle layout coords in GDD | @game_designer | → docs/GDD.md#puzzle-layout
- [ ] W4.3 | Studio: stand on plate opens gate | @human

## DAY 5 — DATA
- [x] W5.1 | BestTime on PlayerRemoving via RunStartedAt | @gameplay_programmer | → src/server/Data/PlayerData.server.luau
- [x] W5.2 | BestTime notes in SYSTEMS | @systems_designer | → docs/SYSTEMS.md
- [x] W5.3 | QA SCORE | @qa_engineer | → docs/QA_REPORT.md
- [x] W5.4 | No HIGH/CRIT — NOTE only | @refactorer

## DAY 6 — POLISH
- [x] W6.1 | Juice documented in GDD | @game_designer | → docs/GDD.md#juice
- [x] W6.2 | RELEASE smoke includes coins+plate+void | @builder | → docs/RELEASE.md
- [x] W6.3 | Integrator remotes cross-check OK | @integrator
- [ ] W6.4 | Studio full smoke 10 min | @human

## DAY 7 — FREEZE
- [x] W7.1 | Full QA SCORE 86 | @qa_engineer | → docs/QA_REPORT.md
- [x] W7.2 | No HIGH/CRIT to fix | @refactorer
- [x] W7.3 | SCORE ≥ 80 documented | @qa_engineer | → docs/QA_REPORT.md
- [ ] W7.4 | Human final accept / ship | @human

## BACKLOG (done early — optional Studio check)
- [x] W9.1 | MovingPlatforms Mover1 Z -20↔-80 | @gameplay_programmer | → src/server/Level/MovingPlatforms.server.luau
- [x] W9.2 | Leaderboard.client stub UI | @client_programmer | → src/client/Leaderboard.client.luau
