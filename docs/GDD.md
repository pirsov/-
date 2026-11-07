# Game Design Document — Puzzle Platformer Obby

## Core Loop
- Genre: Puzzle Platformer (obby-style level progression)
- Player solves puzzles to open paths forward
- Collects coins and power-ups along the way
- Reaches checkpoints that save progress and reset on death
- Final boss fight ends the level

## Win / Lose Conditions + Scoring
- Win: reach the final checkpoint after defeating the boss
- Lose: fall into void or lethal damage -> respawn at last checkpoint (does not end run)
- Score = time_seconds + (coins * 10) - (boss_defeated * 1000)
- Leaderboard: sorted by score ascending (faster + more coins wins)

## MVP Features
1. Puzzle solving mechanics: 3 types (button press, pressure plate, sequence)
2. Level progression: 5 sections, each ends with a checkpoint
3. Checkpoint creation and respawn
4. Leaderboard (DataStore, top 10 per server)
5. Sound effects: jump, checkpoint, coin, win, lose
6. HUD: timer, coin count, current checkpoint number
7. Save and autosave: checkpoint progress + best score
8. Mobile touch controls in addition to PC keyboard

## Week Goals
- Checkpoint gaps (studs along −Z): **50 / 70 / 90 / 110 / 130**
- Coin spawn height: **Y = 7**
- Coin counts per section (Day 2): **5 / 5 / 5 / 5 / 8**
- Void soft-fail below **Y = −20** → LoadCharacter
- Pressure plate: see Puzzle Layout

## Sections (playable layout)
1. Intro platform → Checkpoint1 (gap 50)
2. Pressure-plate lane → Checkpoint2 (gap 70)
3. Coin field → Checkpoint3 (gap 90)
4. Combo stretch → Checkpoint4 (gap 110)
5. Final approach → Checkpoint5 (gap 130)

## Map (Generator)
- `workspace.Map.Path` — continuous floor (width 28) from spawn Z=+20 through CP5
- `workspace.Map.SpawnPlaza` + `SpawnLocation` — start pad
- Soft rails left/right; default `Baseplate` removed
- Floor top **Y = 5**; checkpoints sit on the path

## Puzzle Layout
- **PressurePlate** Part at `(8, 5.5, −30)`, size `(6, 1, 6)`, color blue
- **Gate** Part at `(8, 11, −40)`, size `(10, 12, 1)`; opens (CanCollide=false, Transparency=0.7) while player stands on plate

## Juice
- CheckpointReached: HUD CheckpointCount flash (BackgroundTransparency 0.1→0.5) + sound `9112854440`
- CoinCollected: CoinCount flash + sound `9114224690`
