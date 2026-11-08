# LAST_UPDATE: STUDIO FIX after greenfield — LevelConfig JS syntax killed Generator
# Do NOT wipe src. Answer `n` at H1, pull this TZ, then: python run.py --week
# AFTER: python run.py --eval

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n

## AGENT G — already DONE (keep files; do not recreate from empty)
- [x] G1 | Remotes | @integrator | → src/shared/Gameplay/Remotes.luau
- [x] G2 | InitRemotes | @gameplay_programmer | → src/server/InitRemotes.server.luau
- [x] G3 | LevelConfig (BROKEN — JS colon syntax) | @content_author | → src/shared/Content/LevelConfig.luau
- [x] G4 | Generator | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [x] G5 | Checkpoints | @gameplay_programmer | → src/server/Gameplay/Checkpoints.server.luau
- [x] G6 | Coins (BROKEN — Destroy hit.Parent / WaitForChild Coins) | @gameplay_programmer | → src/server/Gameplay/Coins.server.luau
- [x] G7 | Void | @gameplay_programmer | → src/server/Gameplay/Void.server.luau
- [x] G8 | Puzzles | @gameplay_programmer | → src/server/Gameplay/Puzzles.server.luau
- [x] G9 | PlayerData | @gameplay_programmer | → src/server/Data/PlayerData.server.luau
- [x] G10 | HUD (BROKEN — characterAdded nil) | @client_programmer | → src/client/HUD.client.luau
- [x] G11 | Effects | @client_programmer | → src/client/Effects.client.luau
- [x] G12 | Leaderboard (BROKEN — WaitForChild LeaderboardFrame) | @client_programmer | → src/client/Leaderboard.client.luau
- [x] G13 | GDD | @game_designer | → docs/GDD.md#greenfield-layout
- [x] G14 | QA_REPORT | @qa_engineer | → docs/QA_REPORT.md
- [x] G15 | Example | @refactorer | → src/server/Example.server.luau

## AGENT F — Studio crash fixes (REWRITE; use templates; Luau only)
- [ ] F1 | REWRITE LevelConfig: return { { id = 1, gap = 50, coins = 5 }, { id = 2, gap = 70, coins = 5 }, { id = 3, gap = 90, coins = 5 }, { id = 4, gap = 110, coins = 5 }, { id = 5, gap = 130, coins = 8 } } — Luau `=` ONLY, never `id:` / `sections:` | @gameplay_programmer | → src/shared/Content/LevelConfig.luau
- [ ] F2 | REWRITE Coins: FindFirstChild/ensure Coins folder; ChildAdded; coin:Destroy(); GetPlayerFromCharacter; FireClient(plr); NEVER hit.Parent:Destroy; NEVER bare WaitForChild("Coins") | @gameplay_programmer | → src/server/Gameplay/Coins.server.luau
- [ ] F3 | REWRITE HUD: Instance.new ScreenGui+labels Time/CP/Coins/Best; CheckpointReached+CoinCollected; player.CharacterAdded — NEVER bare characterAdded | @client_programmer | → src/client/HUD.client.luau
- [ ] F4 | REWRITE Leaderboard: Instance.new ScreenGui+TextLabel "Leaderboard (waiting...)"; Remotes.UpdateLeaderboard only — NEVER WaitForChild LeaderboardFrame / RequestLeaderboard | @client_programmer | → src/client/Leaderboard.client.luau
- [ ] F5 | REWRITE Effects: GetService Players; pcall Sound rbxassetid://9112854440 and 9114224690 only | @client_programmer | → src/client/Effects.client.luau

## HUMAN GATES (re-test after F*)
- [ ] H1 | Studio: [Generator] map floor ready; Path+green CPs; no LevelConfig parse error | @human
- [ ] H2 | Studio: coin+CP HUD; no Infinite yield Coins/LeaderboardFrame; no bad SoundId | @human
- [ ] H3 | Studio: plate/gate + void respawn | @human
- [ ] H4 | Final accept then run: python run.py --eval | @human
