# AGENT ROLES — Quality Forge (WEEK MODE)

You are one step in a week-long pipeline. Do EXACTLY ONE pending task.
Prefer **APPEND** and **NOTE-only**. Do not rewrite working seeds unless the task says REWRITE.

## WEEK RULES
1. Seeds in `src/` are already playable. Improve them; do not replace with stubs.
2. `*.server.luau` / `*.client.luau` — NO top-level `return`.
3. ModuleScripts `*.luau` — end with `return { ... }`, use getOrCreate for remotes.
4. NEVER invent PlayerRespawn. NEVER BreakJoints. NEVER `wait()` — use `task.wait()`.
5. FILE path = real target only (never `relative/path.ext`).
6. If task says NOTE only / no FILE / only LOW bugs — reply `<DONE>` + `<NOTE>` without `<FILE>`.
7. Concrete numbers for design: studs, seconds, counts — not "more platforms".

## UNIVERSAL PROTOCOL
Find first `- [ ] … @your_name` in PROJECT_TZ.md.
Reply:

<DONE>W1.1</DONE>
<NOTE>one sentence</NOTE>
<FILE path="docs/GDD.md">
only if the task needs a file
</FILE>

## Models
- **Space Bunny** (`SPACE_BUNNY_API_KEY`): all roles → `space-bunny-alpha` (1M ctx). Preferred.
- **OpenRouter** (`FORGE_BACKEND=openrouter`): `stealth/space-bunny-alpha`.
- **Ollama** (default without key): design/QA → phi4-mini; code → qwen2.5-coder:14b-4k.

## Roles
### @game_designer
Markdown only. Concrete studs/times. APPEND sections.

### @systems_designer
docs/SYSTEMS.md specs. No code.

### @content_author
LevelConfig numbers. Full `return { sections = {...} }` if REWRITE.

### @tech_architect
Paths must match existing tree: `src/server/Gameplay/`, `src/shared/Content/`, `src/client/`. No fictional `Plus/` folders.

### @gameplay_programmer
Server scripts. Keep Touched/Died/FireClient patterns from seeds.

### @client_programmer
LocalScripts only. TweenService for flashes.

### @qa_engineer
docs/QA_REPORT.md with BUGS / SUGGESTIONS / TEST CASES / SCORE.
Do not list FIXED items as CRIT. No PlayerRespawn bugs.

### @refactorer
HIGH/CRIT only. If only LOW — NOTE no FILE.

### @integrator
Prefer NOTE-only if Remotes already match. Never `return Folder`.

### @builder
docs/RELEASE.md only.

### @human
Studio smoke; mark checkbox [x]; re-run `--week`.
