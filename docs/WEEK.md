# Week mode — leave it running, grow quality

## One-time setup
```powershell
cd C:\Users\sv244\Desktop\--cursor-quality-forge-orchestrator-9409
git pull
```

### Backend A — Space Bunny Alpha (recommended, 1M context, free)
Get a key: https://spacebunnymodel.com/get-jev  
Docs: https://github.com/codaaiteam/awesome-space-bunny

```powershell
$env:SPACE_BUNNY_API_KEY = "sb_live_..."   # or set permanently in System env
# optional: $env:FORGE_BACKEND = "spacebunny"
python run.py --doctor
python run.py --validate
```

OpenRouter alternative:
```powershell
$env:OPENROUTER_API_KEY = "sk-or-..."
$env:FORGE_BACKEND = "openrouter"   # model: stealth/space-bunny-alpha
```

### Backend B — local Ollama (default if no cloud key)
```powershell
ollama serve
python run.py --doctor
python run.py --validate
```

## Studio playtest (important)
Those red DataStore / `WaitForChild("Remotes")` errors mean you opened an **old** place file. Current `src/` is Studio-safe.

**Preferred:**
```powershell
git pull
rojo serve
# Studio → Rojo plugin → Connect (live sync from src/)
```

**Or rebuild the place file first:**
```powershell
git pull
.\scripts\rebuild-place.ps1
# Studio → File → Open from File → build/game.rbxlx
```

Notes:
1. PlayerData **does not call DataStore in Studio** (offline attributes). No publish needed for smoke.
2. Optional live DataStore: publish place → enable Studio API Access → `game:SetAttribute("EnableStudioDataStore", true)`.
3. If Output still shows old DataStore stacks — you are not on the rebuilt place / not Connected to Rojo.

## Who writes the game
See [FORGE_CONTRACT.md](FORGE_CONTRACT.md): **LLM via `--week`**, not Cursor hand-edits.
First pending lines in `PROJECT_TZ.md` are **AGENT SPRINT** (`A1`…). Human `y/n` gates come after.

## Start the week
```powershell
$env:FORGE_BACKEND = "openrouter"   # or SPACE_BUNNY_API_KEY
python run.py --week
# model writes A1, A2, … then pauses on @human for Studio y/n
```

When it prints `HITL` and asks `y/n`:
1. Open place in Studio (Rojo or `build/game.rbxlx`)
2. Smoke-test what the task says (checkpoint, coin, plate, void, …)
3. Back in the terminal type `y` → marks the task `[x]` and continues the week
4. Or type `n` → stops; re-run `--week` later

Non-interactive / CI: `python run.py --week --yes` or `$env:FORGE_HITL_AUTO='y'`

## What changed in the system
- **Seeds first:** Generator, Coins, Void, Puzzles, HUD coins, Remotes+CoinCollected already valid
- **Day 1–7 TZ:** tiny APPEND / NOTE-only tasks, not giant rewrites
- **Models:** prefer Space Bunny Alpha (`SPACE_BUNNY_API_KEY`); else Ollama 14b code / phi design
- **No micro-split:** failed code task is SKIPPED, seed kept, pipeline continues
- **Gate:** every 5 steps `--validate` or stop

## Daily budget
- Agent: hours unattended between human gates
- You: ~10 min Studio per day (W1.5, W2.4, W3.4, W4.3, W6.4, W7.4)
