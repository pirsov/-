---
name: roblox-code-maintenance-refactor
source: heuristic
max_chars: 1200
---
---
name: roblox-code-maintenance-refactor
---
# Roblox Code Maintenance Refactor
## Goal
Improve code health without changing player-facing behavior accidentally.
## Refactor Rules
- Read before editing.
- Keep changes scoped.
- Preserve remote contracts unless intentionally migrating.
- Avoid mixing behavior changes with cleanup.
- Playtest after meaningful refactors.
- Check console output.
## Targets
- Duplicated constants and reward formulas.
- Large scripts with mixed responsibilities.
- Client/server boundary confusion.
- Dead remotes, stale UI paths, unused modules.
- Repeated event connection patterns.
- Unclear names around valuable state.
- Magic numbers that should be balance tables.
## Finding Deepening Opportunities
- Where does understanding one concept require bouncing between many tiny scripts?
- Where were pure helpers extracted only for tidiness, but the real bugs live in how they're called (no locality)?
- Where do client and server share a responsibility that leaks across the remote boundary?
## MCP Workflow
1. Use `script_grep` to find duplication, old names, or call sites.
2. Rea