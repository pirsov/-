# Release Checklist (Week build)

## Rojo Build
```sh
rojo build default.project.json --output build/game.rbxlx
```

## Smoke before publish
1. **Checkpoints** — touch CP1..CP5; HUD CP updates; death respawns at last CP
2. **Coins** — yellow cylinders; HUD Coins increments; pickup sound
3. **Void** — fall below Y=-20 respawns (no Health=0 hacks)
4. **Pressure plate** — blue plate at (12,5,-30) opens red gate at (12,11,-40)
5. **Output** — no red errors from Remotes/HUD/Generator

## Publish
1. Build `build/game.rbxlx`
2. Upload / publish place
3. Bump notes in this file
4. Keep `PROJECT_TZ.md` Day 7 human gate checked

## Post-release
- Watch DataStore warnings in live servers
- Collect whether BestTime persists across sessions
