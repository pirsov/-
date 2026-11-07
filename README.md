# Quality Forge — agent makes the game

**Contract:** LLM agent writes `src/` + design docs via `python run.py --week`.  
Cursor only maintains the forge (`docs/FORGE_CONTRACT.md`).

## Start (Windows)
```powershell
git pull
$env:FORGE_BACKEND = "openrouter"          # or set SPACE_BUNNY_API_KEY
$env:OPENROUTER_API_KEY = "sk-or-..."
python run.py --doctor
python run.py --validate
python run.py --week
```

First pending tasks are **AGENT SPRINT** (`A1`…) — the model edits the game.  
`@human` Studio gates come after; answer `y`/`n` in the terminal.

Local fallback without a cloud key: Ollama `qwen2.5-coder:14b-4k`.

Details: [docs/WEEK.md](docs/WEEK.md) · [docs/FORGE_CONTRACT.md](docs/FORGE_CONTRACT.md)
