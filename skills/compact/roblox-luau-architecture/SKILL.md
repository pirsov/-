---
name: roblox-luau-architecture
source: heuristic
max_chars: 1200
---
---
name: roblox-luau-architecture
---
# Roblox Luau Architecture
## Goal
## MCP Workflow
1. Start with `list_roblox_studios`, `set_active_studio` if needed, and `get_studio_state`.
2. Locate code with `script_search` or `script_grep`.
3. Read relevant scripts with `script_read` before editing.
4. Apply edits with `multi_edit`.
5. Playtest with `start_stop_play`.
6. Check `get_console_output` for regressions.
## Placement Rules
- Put authoritative game logic in `ServerScriptService` or server-owned modules.
- Put shared constants, type definitions, remotes, and pure shared helpers in `ReplicatedStorage`.
- Put player input, camera, local-only UI, and visual prediction in client scripts.
- Keep workspace scripts rare and intentional; prefer service-style scripts that manage tagged instances or configured folders.
- Avoid scattering duplicated constants across client and server.
## Remote Boundaries
- Treat every client remote payload as untrusted.
- Prefer narrow remotes with explicit action names and typed payload checks.
- Rate-limit player-triggered remotes that can affect economy, inventory, combat, or plac