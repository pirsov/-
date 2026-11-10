---
name: forge-luau-touch
source: forge-learned
max_chars: 700
---
# Touch + void

- Parts that must fire Touched: `CanTouch = true`.
- Destroy the **coin Part**, never `hit` / `hit.Parent` (character).
- Void: Heartbeat if HRP.Y < -20 then LoadCharacter (not Touched-on-HRP).
- Puzzles: Touched open, TouchEnded close — never `.Left`.
