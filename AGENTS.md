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

## Roles
### @game_designer — phi4-mini
Markdown only. Concrete studs/times. APPEND sections.

### @systems_designer — phi4-mini
docs/SYSTEMS.md specs. No code.

### @content_author — phi4-mini
LevelConfig numbers. Full `return { sections = {...} }` if REWRITE.

### @tech_architect — 14b
Paths must match existing tree: `src/server/Gameplay/`, `src/shared/Content/`, `src/client/`. No fictional `Plus/` folders.

### @gameplay_programmer — 14b-4k
Server scripts. Keep Touched/Died/FireClient patterns from seeds.

### @client_programmer — 14b-4k
LocalScripts only. TweenService for flashes.

### @qa_engineer — phi4-mini
docs/QA_REPORT.md with BUGS / SUGGESTIONS / TEST CASES / SCORE.
Do not list FIXED items as CRIT. No PlayerRespawn bugs.

### @refactorer — 14b-4k
HIGH/CRIT only. If only LOW — NOTE no FILE.

### @integrator — 14b-4k
Prefer NOTE-only if Remotes already match. Never `return Folder`.

### @builder — phi4
docs/RELEASE.md only.

### @human
Studio smoke; mark checkbox [x]; re-run `--week`.
