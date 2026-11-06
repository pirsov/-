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
