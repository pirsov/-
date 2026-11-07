# Week mode — leave it running, grow quality

## One-time setup
```powershell
cd C:\Users\sv244\Desktop\--cursor-quality-forge-orchestrator-9409
git pull
python run.py --doctor
python run.py --validate
```

## Studio playtest (important)
1. Prefer **Rojo sync** (`rojo serve` + Rojo plugin Connect) — do **not** rely on old `build/game.rbxlx` alone.
2. DataStore warning *"publish this place"* is normal for unpublished places. PlayerData now runs in **offline Studio mode** (attributes only).
3. Optional real DataStore: publish the place → Game Settings → Security → **Enable Studio Access to API Services**.
4. If you see `WaitForChild("Remotes")` infinite yield — you are on **stale client scripts**; git pull + Rojo resync.

## Start the week
```powershell
python run.py --week
# = loop max 200, sleep 30s, validate every 5 steps, no micro-split, 14b for code
```

When it prints `HITL` / waiting human:
1. Open place in Studio (Rojo or `build/game.rbxlx`)
2. Touch checkpoint, pick coin, stand on blue plate, fall into void
3. In `PROJECT_TZ.md` change that day's `- [ ] W… @human` to `- [x]`
4. `python run.py --week` again

## What changed in the system
- **Seeds first:** Generator, Coins, Void, Puzzles, HUD coins, Remotes+CoinCollected already valid
- **Day 1–7 TZ:** tiny APPEND / NOTE-only tasks, not giant rewrites
- **Models:** code roles → `qwen2.5-coder:14b-4k` only; design/QA → phi4-mini
- **No micro-split:** failed code task is SKIPPED, seed kept, pipeline continues
- **Gate:** every 5 steps `--validate` or stop

## Daily budget
- Agent: hours unattended between human gates
- You: ~10 min Studio per day (W1.5, W2.4, W3.4, W4.3, W6.4, W7.4)
