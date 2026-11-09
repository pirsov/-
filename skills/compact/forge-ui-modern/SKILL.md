---
name: forge-ui-modern
source: forge-learned
max_chars: 1100
---
# Modern UI (Roblox + Forge control UI)

## Roblox ScreenGui
- Create ScreenGui ResetOnSpawn=false; use TextButton with UICorner + UIStroke (procedural, no image spam).
- Hover: TweenService BackgroundColor3 / UIScale 1.0->1.04; click: brief scale 0.96.
- Layout: UIListLayout / UIPadding; avoid overlapping absolute positions when stacking.
- Read Player attrs for HUD; never Character attrs.

## Forge control panels 1-5
- Unlock in order: project -> goal/skills -> TZ -> week run -> smoke.
- Disable later panels until prior stage done (progress JSON).
- Buttons: clear primary action per panel; show status pill running/done/error.
- Live log auto-scroll; code viewer monospace; keep motion subtle (opacity/border only).
