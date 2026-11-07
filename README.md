# Quality Forge — long-horizon Roblox game factory

Leave it running (or resume after pause) and get a detailed, playable game.

## Quick start

```bash
# one step
python run.py

# unattended (days/week) — pauses on @human gates
python run.py --loop --max 500

# optional pacing between steps
python run.py --loop --max 500 --sleep 2

# gates
python run.py --validate
python run.py --score
```

Windows PowerShell (same mechanic):

```powershell
.\run.ps1
.\run.ps1 -Loop -Max 500
```

Requires [Ollama](https://ollama.com) at `http://localhost:11434` with coder models
(`qwen2.5-coder:7b` / `14b`). Unit tests do not need Ollama:

```bash
python -m unittest tests.test_orchestrator -v
```

## Mechanic (Quality Forge)

| Pass | Purpose |
|------|---------|
| BLUEPRINT | GDD + architecture + remotes |
| SKELETON / SYSTEMS | one real module per task |
| CRITIQUE LOOP | QA → fix until score ≥ 80 |
| POLISH | juice, void, UX |
| HARDEN | integrator + human Studio gate |
| DEEPEN | backlog (moving platforms, leaderboard, more sections) |

State lives in `PROJECT_TZ.md`. Heartbeat: `.forge/state/heartbeat.json`.
Snapshots before every write: `.forge/snapshots/`.

## Bugs fixed in the orchestrator

1. **APPEND overwrote files** — mode is parsed from the task; APPEND always appends.
2. **DONE without `<FILE>` counted as success** — rejected when task has `→ path`.
3. **No rollback** — validator failure restores snapshot.
4. **No feedback on retry** — validator errors injected into the next prompt.
5. **39KB prompt blowups** — only relevant files, 24k char budget.
6. **`num_predict=600` truncated code** — 2k–4k by role, escalates on retry.
7. **`wait()` slipped through** — validator forbids it; requires `task.wait`.
