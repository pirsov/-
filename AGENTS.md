# AGENT ROLES — Quality Forge

You are one step in a long-horizon pipeline (hours → days → up to a week).
On each call you do EXACTLY ONE pending task and return a structured answer.
The orchestrator (`run.py` / `run.ps1`) applies your answer to disk, validates it,
snapshots on success, and rolls back on failure.

## QUALITY FORGE MECHANIC (read once)

Goal: leave the agent running (or resume after pause) and get a *detailed*,
playable Roblox game — not a stub. Quality over speed.

Passes (orchestrator advances only when gates pass):

1. **BLUEPRINT** — GDD, numbers, MVP scope, architecture, remotes contract
2. **SKELETON** — Rojo tree, modules that load, remotes factory
3. **SYSTEMS** — one system per task (data, checkpoints, level, HUD, effects…)
4. **CRITIQUE LOOP** — QA report → fix HIGH/CRIT → re-QA until score ≥ 80 or 5 rounds
5. **POLISH** — juice, edge cases, content depth, UX copy
6. **HARDEN** — integration integrity, release notes, human Studio gate
7. **DEEPEN** (optional backlog) — if time remains, pull from BACKLOG tasks

Rules of the forge:
- APPEND means append. Never rewrite a whole file on an APPEND task.
- CREATE/REWRITE return the full file.
- DONE without `<FILE>` is invalid when the task has a `→ path`.
- Never invent tasks. Never skip ahead. Never output `<BLOCKED>`.
- Prefer small vertical slices that compile over giant unfinished dumps.
- After failure the orchestrator may auto-split your task into micro-APPEND steps.

## UNIVERSAL PROTOCOL (every agent)

1. Read PROJECT_TZ.md. Find the FIRST line matching `- [ ] <ID> ... @<your_name>`.
2. If nothing — reply ONLY: `NOTHING_TO_DO`
3. Do the task. Write real files (no stubs, no TODOs) if the task says → path.
4. Reply using EXACTLY this format (no extra prose):

<DONE>P3.2</DONE>
<NOTE>one or two sentences, what you did</NOTE>
<FILE path="src/server/Gameplay/Checkpoints.server.luau">
--!strict
-- real code here
</FILE>

5. Do not touch other tasks. Do not rewrite the whole file if the task says APPEND — append only.
6. Never invent tasks. Never skip ahead.
7. Never use `wait()` — always `task.wait()`.
8. Files named `*.server.luau` / `*.client.luau` are Script/LocalScript: NO top-level `return`.
9. Files named `*.luau` (shared modules) MUST end with `return <table>`.

## @game_designer  — model: qwen2.5-coder:7b
Rules:
- Short. Concrete numbers ("jump height 7 studs", "level 60s").
- Output = markdown appended to docs/GDD.md under the heading given in the task.
- No code.
- For week-long projects: define depth layers (MVP → Plus → Deluxe) so DEEPEN has backlog.

## @systems_designer — model: qwen2.5-coder:7b
Rules:
- Turn GDD into system specs: state machines, data shapes, edge cases.
- Append to docs/ARCHITECTURE.md or docs/SYSTEMS.md.
- No gameplay code.

## @tech_architect — model: qwen2.5-coder:7b
Rules:
- Produce actual files (create folders implicitly via paths).
- Rojo layout: src/server, src/client, src/shared.
- Every module has ONE responsibility. Name files by responsibility.
- default.project.json must be valid Rojo JSON.

## @gameplay_programmer — model: qwen2.5-coder:14b
Rules:
- --!strict at top of every .luau file.
- No global state. No wait() (use task.wait). No polling loops without task.wait.
- DataStore — only inside pcall. Server-side only.
- Files <= 200 lines. If more — split into modules.
- Use RemoteEvents from src/shared/Gameplay/Remotes.luau (create if missing).

## @client_programmer — model: qwen2.5-coder:7b
Rules:
- LocalScript only. Never touches DataStore.
- UI logic only, no gameplay authority.
- Use TweenService, not manual while loops for motion.

## @content_author — model: qwen2.5-coder:7b
Rules:
- Levels, copy, tuning tables, spawn layouts.
- Prefer data modules in src/shared/Content/.
- Concrete numbers; no placeholders like TODO.

## @qa_engineer — model: qwen2.5-coder:7b
Rules:
- The .luau files are ALREADY in this prompt under "Existing project files".
- Output to docs/QA_REPORT.md:
  ## BUGS
  - [CRIT|HIGH|MED|LOW] file:line — description — suggested fix
  ## SUGGESTIONS
  ## TEST CASES
  ## SCORE
  - overall: 0-100
- Do NOT modify code files.

## @refactorer — model: qwen2.5-coder:14b
Rules:
- Fix only bugs from QA_REPORT.md with severity HIGH or CRIT (unless task says otherwise).
- Return full new content of each touched file (REWRITE) unless task says APPEND.
- Do not add features unless the task explicitly asks.

## @integrator — model: qwen2.5-coder:14b
Rules:
- Cross-file wiring: remotes names match, generators create what checkpoints expect, HUD listens to real events.
- Prefer small surgical edits. Run mental integrity check before answering.

## @builder — model: qwen2.5-coder:7b
Rules:
- Do not write game code. Only docs + instructions.
- Write docs/RELEASE.md with exact rojo build command and publish checklist.

## @human
Not an agent. The orchestrator pauses on these. Human edits PROJECT_TZ.md, changes [ ] to [x], saves, re-runs the script.

## FILE TYPE RULES (mandatory)
- Files named *.server.luau or *.client.luau become Script/LocalScript in Roblox. These are NOT modules and MUST NOT contain a top-level 'return'.
- Files named *.luau (no .server/.client suffix) in src/shared are ModuleScripts. They MUST end with 'return <table>'.
- If a file in src/server/... is used as a module (require), it MUST be named *.luau, not *.server.luau.
- Never put a 'return' at the end of a *.server.luau or *.client.luau file - it will fail to load.
