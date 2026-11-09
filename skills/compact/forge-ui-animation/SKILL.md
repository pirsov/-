---
name: forge-ui-animation
source: forge-learned
max_chars: 900
---
# UI animation budget

- 2-3 intentional motions max per view (enter fade, hover, success pulse).
- Prefer opacity + transform; avoid glow stacks and purple gradients.
- Roblox: TweenInfo.new(0.15-0.25, Quad, Out); cancel previous tween on re-hover.
- Forge web: CSS transitions 160-220ms on border-color/opacity; no infinite spinners except running state.
- Respect reduced motion if available.
