# Quality Forge (Week Mode)

Leave the agent running for days; quality grows via **seeds + tiny tasks + daily Studio gates**.

## Start
```powershell
git pull
python run.py --doctor
python run.py --validate
python run.py --week
```

Details: [docs/WEEK.md](docs/WEEK.md)

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
