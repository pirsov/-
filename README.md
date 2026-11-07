# Quality Forge (Week Mode)

Leave the agent running for days; quality grows via **seeds + tiny tasks + daily Studio gates**.

## Start
```powershell
git pull
# Recommended: Space Bunny Alpha (1M ctx, free) — https://spacebunnymodel.com/get-jev
$env:SPACE_BUNNY_API_KEY = "sb_live_..."
python run.py --doctor
python run.py --validate
python run.py --week
```

Without a cloud key the forge falls back to local Ollama (`qwen2.5-coder:14b-4k`).

Details: [docs/WEEK.md](docs/WEEK.md) · Space Bunny: [awesome-space-bunny](https://github.com/codaaiteam/awesome-space-bunny)

## What you get out of the box
Playable MVP skeleton already in `src/`:
- Checkpoints + LoadCharacter respawn
- Coins + CoinCollected remote
- Generator from LevelConfig
- Void (Y &lt; -20)
- Pressure plate puzzle
- HUD (time / CP / coins) + sounds

## Week loop
Day 1 docs lock → Day 2 generator tune → Day 3 HUD/FX → Day 4 puzzle → Day 5 data → Day 6 polish → Day 7 QA freeze.

Human ~10 min/day on `@human` tasks in `PROJECT_TZ.md`.
