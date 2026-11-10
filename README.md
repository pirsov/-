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

**Greenfield:** `src/` starts empty. Sprint **G1–G15** makes the LLM CREATE Remotes → Generator → gameplay → HUD.  
Then `@human` H1–H4 with terminal `y`/`n`.

Local fallback without a cloud key: Ollama `qwen2.5-coder:14b-4k`.

**UI (chat / HITL / 24h):** `python -u run.py --ui` → http://127.0.0.1:8787 — см. [README_UI.md](README_UI.md).  
Next core: [docs/A10_PLAN.md](docs/A10_PLAN.md) (DataStore & Networking).

Details: [docs/WEEK.md](docs/WEEK.md) · [docs/FORGE_CONTRACT.md](docs/FORGE_CONTRACT.md)
