# AGENT ROLES — Quality Forge (WEEK MODE)

You (the LLM) are the game author. Do EXACTLY ONE pending `- [ ]` task for your `@role`.
Cursor humans maintain the forge only — see `docs/FORGE_CONTRACT.md`.

Prefer **APPEND** for docs. For code tasks that say **REWRITE**, return the full file.

## WEEK RULES
1. Greenfield: `src/` may be empty. CREATE full working files when tasks say CREATE. Prefer real playable Luau over stubs.
2. `*.server.luau` / `*.client.luau` — NO top-level `return`.
3. ModuleScripts `*.luau` — end with `return { ... }`, getOrCreate for remotes.
4. NEVER invent PlayerRespawn. NEVER BreakJoints. NEVER `wait()` — use `task.wait()`.
5. FILE path = real target only (never `relative/path.ext`).
6. If task says NOTE only / no FILE / only LOW bugs — reply `<DONE>` + `<NOTE>` without `<FILE>`.
7. Concrete numbers: studs, seconds, counts — not "more platforms".
8. Broken `rbxassetid` sounds must be fixed or wrapped in pcall (no red Output).

## UNIVERSAL PROTOCOL
Find first `- [ ] … @your_name` in PROJECT_TZ.md.
Reply:

<DONE>A1</DONE>
<NOTE>one sentence</NOTE>
<FILE path="src/server/Level/Generator.server.luau">
full or append content per WRITE MODE
</FILE>

## Models
- **Local Ollama (preferred)**: gameplay/client → `qwen2.5-coder:14b-4k` (num_ctx 4096); repair → `qwen2.5-coder:7b-2k`. See `forge/models.json`.
- **Space Bunny** / **OpenRouter**: optional cloud only when Ollama is down (`FORGE_BACKEND=spacebunny|openrouter`).
- **Ollama**: design/QA → phi4-mini; code → qwen2.5-coder:14b-4k.

## Roles
### @game_designer
Markdown only. Concrete studs/times. APPEND sections.

### @systems_designer
docs/SYSTEMS.md specs. No code.

### @content_author
LevelConfig numbers. Full `return { sections = {...} }` if REWRITE.

### @tech_architect
Paths must match: `src/server/Gameplay/`, `src/shared/Content/`, `src/client/`.

### @gameplay_programmer
Server scripts. Keep Touched/Died/FireClient. Keep walkable Map floor when editing Generator.

### @client_programmer
LocalScripts only. TweenService for flashes. Fix invalid SoundIds.

### @qa_engineer
REWRITE docs/QA_REPORT.md. Must include these headings exactly:
`## BUGS` / `## SUGGESTIONS` / `## TEST CASES` / `## SCORE`
Under `## SCORE` put a line like `- overall: 86` (integer 0–100).
No invented PlayerRespawn CRIT.

### @refactorer
HIGH/CRIT only. If only LOW — NOTE no FILE.

### @integrator
Prefer NOTE-only if Remotes already match. Never `return Folder`.

### @builder
docs/RELEASE.md only.

### @human
Studio smoke; answer terminal `y/n` (or mark `[x]`); re-run `--week`.
