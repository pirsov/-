# Forge contract — who writes what

## Rule
**The LLM agent (via `python run.py --week`) writes the game.**  
Cursor / cloud coding agents maintain **only** the forge (orchestrator, validators, prompts, model backends). They must **not** close `@gameplay_programmer` / `@client_programmer` / design TZ tasks by hand-editing `src/` or `docs/` as a substitute for a model run.

## Allowed for Cursor
- `forge/*`, `run.py`, `tests/*`, bootstrap, HITL y/n, LLM backends
- Validators that reject stubs / bad paths
- Minimal **bootstrap seeds** so Studio opens without crashing (Remotes getOrCreate, InitRemotes, offline PlayerData guard)
- Docs that explain how to run the agent

## Forbidden for Cursor
- Implementing map, puzzles, HUD juice, LevelConfig balance, QA reports as “done” in TZ
- Mass-checking `[x]` on agent roles without a successful forge step + model FILE write
- Replacing a failed Ollama run by rewriting the game yourself

## How the game grows
1. Add `- [ ] … @role` tasks in `PROJECT_TZ.md` (agent tasks **above** `@human` gates)
2. `python run.py --week` with Space Bunny / OpenRouter / Ollama
3. Human only answers HITL `y/n` after Studio smoke

## Repair loop (local models)
If the model writes almost-good code and the validator fails (wrong Roblox call, bad name, missing `## SCORE`):
the next attempt is **REPAIR MODE** — same draft in the prompt, “fix only these errors”, not a greenfield rewrite.
Disk is rolled back to the last good seed so Studio stays playable; the draft stays in memory for the model.
