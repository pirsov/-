# LAST_UPDATE: 2026-11-08 Studio smoke showed Baseplate + WaitForChild Checkpoints + bad sound
# FORGE: LLM writes game via --week. Cursor = forge + tiny bootstrap only.
# RUN:  $env:FORGE_BACKEND='ollama'; python run.py --week

## LEGEND
- [ ] pending | [x] done | @human = Studio y/n | other @ = LLM

## QUALITY GATES
- `python run.py --validate` OK
- Studio: Map Path (not only Baseplate), CP>0, coins, plate, no Infinite yield / bad SoundId

---

## AGENT SPRINT B — fix Studio Output from smoke (LLM)
- [ ] B1 | REWRITE Generator from baseline: MUST destroy Baseplate; create workspace.Map.Path + SpawnPlaza + SpawnLocation; workspace.Checkpoints with Checkpoint..id; workspace.Coins; 3 Obstacle per section; print [Generator] map floor ready | @gameplay_programmer | → src/server/Level/Generator.server.luau
- [ ] B2 | REWRITE Effects.client.luau: wrap Sound play in pcall; never use rbxassetid://203785492; use known-good ids OR skip sound on failure; keep HUD flash tweens | @client_programmer | → src/client/Effects.client.luau
- [ ] B3 | QA after B1–B2; ## BUGS ## SUGGESTIONS ## TEST CASES ## SCORE with overall number | @qa_engineer | → docs/QA_REPORT.md
- [ ] B4 | Fix HIGH/CRIT from B3 only; if only LOW — NOTE no FILE | @refactorer

## HUMAN GATES (after B)
- [ ] H1 | Studio: see Map Path + green CPs, not empty Baseplate only; Output has [Generator] map floor ready | @human
- [ ] H2 | Studio: pick coin + CP, no Infinite yield Checkpoints, no Sound asset-type errors | @human
- [ ] H3 | Studio: pressure plate opens gate | @human

## SPRINT A (done on user machine — keep [x] locally if already finished)
- [x] A1 | Generator obstacles | @gameplay_programmer
- [x] A2 | Effects sounds | @client_programmer
- [x] A3 | GDD map-layout | @game_designer
- [x] A4 | LevelConfig | @content_author
- [x] A5 | QA_REPORT | @qa_engineer
- [x] A6 | refactorer NOTE | @refactorer
- [x] W1.5 | Studio smoke | @human
- [x] W2.4 | coins | @human
- [x] W3.4 | feedback | @human
- [x] W4.3 | plate | @human
- [x] W6.4 | full smoke | @human
- [x] W7.4 | accept | @human

## BOOTSTRAP
- Checkpoints creates folder if missing (no infinite WaitForChild)
- PlayerData Studio offline; InitRemotes; Remotes getOrCreate
