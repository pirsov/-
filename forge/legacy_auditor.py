"""A12.0 Legacy auditor — static audit of an external Luau tree for pitfalls.

Use:
  python -u run.py --audit-legacy path/to/legacy_project
  python -u run.py --audit-legacy path/to/legacy_project --forge-root .

Writes (under forge root by default):
  docs/LEGACY_ARCHITECTURE.md
  docs/LEGACY_PITFALLS.md
  .forge/legacy_audit/draft_rules.json  (+ optional merge into knowledge_base as draft)
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

LUAU_GLOBS = ("*.luau", "*.lua")
SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".forge",
    "Packages",
    "ServerPackages",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FunctionInfo:
    name: str
    line: int
    kind: str  # function|local_function|method
    file: str


@dataclass
class ModuleInfo:
    path: str
    lines: int
    functions: List[FunctionInfo] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)


@dataclass
class Pitfall:
    id: str
    severity: str  # crit|high|med
    title: str
    file: str
    line: int
    snippet: str
    why: str
    rule_hint: Dict[str, Any]


# --- heuristics -------------------------------------------------------------

_FN_RE = re.compile(
    r"(?m)^(?P<indent>\s*)(?:local\s+)?function\s+(?P<name>[A-Za-z_][\w\.:]*)\s*\("
)
_LOCAL_FN_RE = re.compile(
    r"(?m)^(?P<indent>\s*)local\s+(?P<name>[A-Za-z_]\w*)\s*=\s*function\s*\("
)
_REQUIRE_RE = re.compile(r"\brequire\s*\(\s*([^)]+)\)")
_SERVICE_RE = re.compile(r'GetService\s*\(\s*["\'](\w+)["\']\s*\)')


def _strip_comments_keep_lines(text: str) -> str:
    """Remove -- comments but keep newlines for line numbers."""
    out: List[str] = []
    for line in text.splitlines():
        # crude: drop -- outside strings (good enough for heuristics)
        if "--[[" in line:
            out.append(re.sub(r"--\[\[.*", "", line))
        else:
            out.append(re.sub(r"--(?!\[\[).*$", "", line))
    return "\n".join(out)


def iter_luau_files(project: Path) -> List[Path]:
    files: List[Path] = []
    if not project.exists():
        return files
    for pat in LUAU_GLOBS:
        for p in project.rglob(pat):
            if any(part in SKIP_DIR_NAMES for part in p.parts):
                continue
            if p.is_file():
                files.append(p)
    return sorted(files)


def decompose_file(path: Path, *, project_root: Path) -> ModuleInfo:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    try:
        rel = path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix().replace("\\", "/")

    functions: List[FunctionInfo] = []
    for m in _FN_RE.finditer(text):
        name = m.group("name")
        kind = "method" if ":" in name or "." in name else "function"
        if m.group(0).lstrip().startswith("local"):
            kind = "local_function"
        line = text[: m.start()].count("\n") + 1
        functions.append(FunctionInfo(name=name, line=line, kind=kind, file=rel))
    for m in _LOCAL_FN_RE.finditer(text):
        line = text[: m.start()].count("\n") + 1
        functions.append(
            FunctionInfo(name=m.group("name"), line=line, kind="local_function", file=rel)
        )

    requires = [m.group(1).strip() for m in _REQUIRE_RE.finditer(text)]
    services = sorted({m.group(1) for m in _SERVICE_RE.finditer(text)})
    return ModuleInfo(
        path=rel,
        lines=text.count("\n") + 1 if text else 0,
        functions=functions,
        requires=requires[:40],
        services=services,
    )


def decompose_project(project: Path) -> List[ModuleInfo]:
    return [decompose_file(p, project_root=project) for p in iter_luau_files(project)]


def _line_at(text: str, idx: int) -> Tuple[int, str]:
    line = text[:idx].count("\n") + 1
    snippet = text.splitlines()[line - 1].strip() if text.splitlines() else ""
    return line, snippet[:160]


def _window_has_pcall(text: str, match_start: int, *, before: int = 400, after: int = 500) -> bool:
    lo = max(0, match_start - before)
    hi = min(len(text), match_start + after)
    return "pcall" in text[lo:hi]


def find_pitfalls(project: Path) -> List[Pitfall]:
    pitfalls: List[Pitfall] = []
    n = 0

    def add(
        *,
        severity: str,
        title: str,
        file: str,
        line: int,
        snippet: str,
        why: str,
        rule_hint: Dict[str, Any],
    ) -> None:
        nonlocal n
        n += 1
        pitfalls.append(
            Pitfall(
                id=f"P{n:03d}",
                severity=severity,
                title=title,
                file=file,
                line=line,
                snippet=snippet,
                why=why,
                rule_hint=rule_hint,
            )
        )

    for path in iter_luau_files(project):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            rel = path.resolve().relative_to(project.resolve()).as_posix()
        except ValueError:
            rel = path.as_posix().replace("\\", "/")
        code = _strip_comments_keep_lines(raw)
        is_client = rel.endswith(".client.luau") or "/client/" in rel.lower()
        is_server = rel.endswith(".server.luau") or "/server/" in rel.lower()

        # 1) DataStore Get/Set/UpdateAsync without nearby pcall
        for m in re.finditer(
            r":\s*(GetAsync|SetAsync|UpdateAsync|IncrementAsync|RemoveAsync)\s*\(",
            code,
        ):
            if _window_has_pcall(code, m.start()):
                continue
            line, snip = _line_at(code, m.start())
            add(
                severity="crit",
                title=f"DataStore {m.group(1)} without pcall",
                file=rel,
                line=line,
                snippet=snip,
                why="DataStore failures throw; without pcall the script dies and progress is lost.",
                rule_hint={
                    # Require pcall in DS files (do NOT forbid :SetAsync itself — that breaks safe pcall wraps)
                    "type": "require_regex",
                    "pattern": r"\bpcall\s*\(",
                    "msg": f"HITL/legacy: wrap DataStore {m.group(1)} in pcall",
                    "match_files": [],
                    "archetypes": ["datastore_service", "server_script"],
                },
            )

        # 2) GetService("DataStoreService") on client
        if is_client and "DataStoreService" in code:
            for m in re.finditer(r"DataStoreService", code):
                line, snip = _line_at(code, m.start())
                add(
                    severity="crit",
                    title="DataStoreService on client",
                    file=rel,
                    line=line,
                    snippet=snip,
                    why="Clients must not touch DataStore — exploit + replication risk.",
                    rule_hint={
                        "type": "forbid_substr",
                        "text": "DataStoreService",
                        "msg": "HITL/legacy: DataStoreService forbidden on client",
                        "match_files": [Path(rel).name],
                        "archetypes": ["client_ui"],
                    },
                )
                break

        # 3) while true / while true do without task.wait / wait in body (same block heuristic)
        for m in re.finditer(r"(?m)^\s*while\s+true\s+do\b", code):
            # look ahead ~800 chars for wait
            chunk = code[m.start() : m.start() + 900]
            if re.search(r"\b(?:task\.wait|wait)\s*\(", chunk):
                continue
            # until matching rough end — if wait missing in window, flag
            line, snip = _line_at(code, m.start())
            add(
                severity="high",
                title="while true do without wait",
                file=rel,
                line=line,
                snippet=snip,
                why="Tight loop freezes the Luau VM / hangs the server or client.",
                rule_hint={
                    "type": "forbid_regex",
                    "pattern": r"while\s+true\s+do(?![\s\S]{0,400}\b(?:task\.wait|wait)\s*\()",
                    "msg": "HITL/legacy: while true do must include task.wait/wait",
                    "match_files": [],
                    "archetypes": ["server_script", "client_ui", "datastore_service"],
                },
            )

        # 4) FireServer on client — remind server must validate (flag if server file has OnServerEvent
        #    without obvious typeof/assert/guard nearby — scanned on server files)
        if is_client and re.search(r":\s*FireServer\s*\(", code):
            for m in re.finditer(r":\s*FireServer\s*\(", code):
                line, snip = _line_at(code, m.start())
                add(
                    severity="med",
                    title="Client FireServer — ensure server validates args",
                    file=rel,
                    line=line,
                    snippet=snip,
                    why="Any client can spoof FireServer args. Server must validate pack/price/ownership.",
                    rule_hint={
                        "type": "require_regex",
                        "pattern": r"OnServerEvent[\s\S]{0,400}(?:typeof|assert|if\s+typeof)",
                        "msg": "HITL/legacy: OnServerEvent handlers must validate args (typeof/assert)",
                        "match_files": [],  # apply to server remotes handlers via archetype
                        "archetypes": ["datastore_service", "server_script"],
                        "advisory": True,
                    },
                )

        # 5) OnServerEvent without typeof/assert in handler window
        if is_server or "OnServerEvent" in code:
            for m in re.finditer(r"\.OnServerEvent\s*:\s*Connect\s*\(\s*function\s*\(", code):
                window = code[m.start() : m.start() + 700]
                if re.search(r"\btypeof\s*\(|\bassert\s*\(", window):
                    continue
                line, snip = _line_at(code, m.start())
                add(
                    severity="high",
                    title="OnServerEvent handler without arg validation",
                    file=rel,
                    line=line,
                    snippet=snip,
                    why="Missing typeof/assert opens an exploit path (free items, illegal packs).",
                    rule_hint={
                        "type": "require_regex",
                        "pattern": r"OnServerEvent[\s\S]{0,500}(?:typeof|assert)",
                        "msg": "HITL/legacy: validate RemoteEvent args on server",
                        "match_files": [Path(rel).name],
                        "archetypes": ["datastore_service", "server_script"],
                    },
                )

        # 6) PlayerRemoving / Player use after potential leave — GetPlayerFromCharacter without nil check
        for m in re.finditer(r"GetPlayerFromCharacter\s*\([^)]*\)\s*(?!\s*[=,)])", code):
            # if next lines don't check nil
            after = code[m.end() : m.end() + 120]
            if re.search(r"\bif\s+not\s+\w+|\bif\s+\w+\s*then|==\s*nil", after):
                continue
            line, snip = _line_at(code, m.start())
            add(
                severity="med",
                title="GetPlayerFromCharacter without nil guard",
                file=rel,
                line=line,
                snippet=snip,
                why="Character may be orphaned after leave; nil player crashes handlers.",
                rule_hint={
                    "type": "forbid_regex",
                    "pattern": r"GetPlayerFromCharacter\s*\([^)]*\)\s*\n(?!\s*if\b)",
                    "msg": "HITL/legacy: nil-check player from GetPlayerFromCharacter",
                    "match_files": [],
                    "archetypes": ["server_script", "client_ui"],
                },
            )

        # 7) wait( without task.wait (deprecated yield)
        for m in re.finditer(r"(?<![\w.])wait\s*\(", code):
            line, snip = _line_at(code, m.start())
            add(
                severity="med",
                title="Deprecated wait() — use task.wait",
                file=rel,
                line=line,
                snippet=snip,
                why="Global wait is throttled/deprecated; prefer task.wait.",
                rule_hint={
                    "type": "forbid_regex",
                    "pattern": r"(?<![\w.])wait\s*\(",
                    "msg": "HITL/legacy: use task.wait, not wait",
                    "match_files": [],
                    "archetypes": ["server_script", "client_ui", "datastore_service"],
                },
            )

    return pitfalls


def pitfalls_to_draft_rules(
    pitfalls: Sequence[Pitfall],
    *,
    start_id: int = 1,
    plugin: str = "legacy.audit",
) -> List[Dict[str, Any]]:
    """Deduplicate rule_hints into knowledge_base-compatible draft rules."""
    rules: List[Dict[str, Any]] = []
    seen: set = set()
    n = start_id
    for p in pitfalls:
        hint = dict(p.rule_hint or {})
        if hint.get("advisory"):
            # still emit but mark advisory — forge feedback ignores unknown fields
            pass
        key = (
            hint.get("type"),
            hint.get("pattern") or hint.get("text"),
            tuple(hint.get("match_files") or []),
            tuple(hint.get("archetypes") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        ctype = hint.get("type") or "forbid_substr"
        check: Dict[str, Any] = {
            "type": ctype,
            "msg": hint.get("msg") or p.title,
        }
        if ctype in {"forbid_regex", "require_regex"}:
            check["pattern"] = hint.get("pattern") or "NEVER"
        else:
            check["text"] = hint.get("text") or p.title[:40]
        checks = [check]
        companion = hint.get("companion_require")
        if isinstance(companion, dict):
            checks.append(
                {
                    "type": companion.get("type") or "require_regex",
                    "pattern": companion.get("pattern") or r"\bpcall\s*\(",
                    "msg": companion.get("msg") or "require pcall",
                }
            )
        # A14 bootstrap: prefer archetypes so rules apply to NEW gens, not only legacy filenames.
        # Keep evidence_file for human review; do not pin match.files when archetypes exist.
        match: Dict[str, Any] = {}
        if hint.get("archetypes"):
            match["archetypes"] = list(hint["archetypes"])
        elif hint.get("match_files"):
            match["files"] = list(hint["match_files"])
        if not match:
            match["files"] = []
        rid = f"R{n:03d}"
        n += 1
        evidence = Path(p.file).name if p.file else ""
        rules.append(
            {
                "id": rid,
                "source": "legacy_audit",
                "plugin": plugin,
                "human_comment": f"{p.title} — {p.why}"[:500],
                "match": match,
                "checks": checks[:3],
                "status": "draft",
                "created_at": now_iso(),
                "from_pitfall": p.id,
                "severity": p.severity,
                "evidence_file": evidence,
            }
        )
    return rules


def render_architecture_md(modules: Sequence[ModuleInfo], *, project: Path) -> str:
    lines = [
        f"# Legacy architecture — `{project.name}`",
        "",
        f"Generated: {now_iso()}",
        f"Modules: **{len(modules)}** · Functions: **{sum(len(m.functions) for m in modules)}**",
        "",
        "## Modules",
        "",
    ]
    for m in modules:
        lines.append(f"### `{m.path}` ({m.lines} lines)")
        if m.services:
            lines.append(f"- Services: {', '.join(m.services)}")
        if m.requires:
            lines.append(f"- require(): {len(m.requires)}")
        if not m.functions:
            lines.append("- (no top-level functions detected)")
        else:
            lines.append("| Line | Kind | Name |")
            lines.append("|------|------|------|")
            for fn in m.functions[:80]:
                lines.append(f"| {fn.line} | {fn.kind} | `{fn.name}` |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_pitfalls_md(pitfalls: Sequence[Pitfall], *, project: Path) -> str:
    lines = [
        f"# Legacy pitfalls — `{project.name}`",
        "",
        f"Generated: {now_iso()}",
        f"Findings: **{len(pitfalls)}**",
        "",
        "This report lists where the code can break or be abused — not how it works.",
        "",
    ]
    by_sev = {"crit": [], "high": [], "med": []}
    for p in pitfalls:
        by_sev.setdefault(p.severity, []).append(p)
    for sev in ("crit", "high", "med"):
        group = by_sev.get(sev) or []
        if not group:
            continue
        lines.append(f"## {sev.upper()} ({len(group)})")
        lines.append("")
        for p in group:
            lines.append(f"### {p.id} — {p.title}")
            lines.append(f"- File: `{p.file}:{p.line}`")
            lines.append(f"- Why: {p.why}")
            lines.append(f"- Snippet: `{p.snippet}`")
            lines.append("")
    if not pitfalls:
        lines.append("_No heuristic pitfalls matched. Tree may be empty or already clean._")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def merge_draft_rules_into_kb(forge_root: Path, draft_rules: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Append draft rules into knowledge_base.json (status stays draft)."""
    from . import feedback

    kb = feedback.load_knowledge(forge_root)
    existing_ids = {str(r.get("id")) for r in (kb.get("rules") or []) if isinstance(r, dict)}
    # renumber collisions
    next_n = 1
    for rid in existing_ids:
        m = re.match(r"R(\d+)$", rid)
        if m:
            next_n = max(next_n, int(m.group(1)) + 1)
    added = 0
    rules = list(kb.get("rules") or [])
    for raw in draft_rules:
        rule = dict(raw)
        if rule.get("id") in existing_ids:
            rule["id"] = f"R{next_n:03d}"
            next_n += 1
        # skip duplicate patterns
        pat = None
        checks = rule.get("checks") or []
        if checks and isinstance(checks[0], dict):
            pat = checks[0].get("pattern") or checks[0].get("text")
        dup = False
        for er in rules:
            if not isinstance(er, dict):
                continue
            ech = (er.get("checks") or [None])[0]
            if isinstance(ech, dict) and (ech.get("pattern") or ech.get("text")) == pat and pat:
                dup = True
                break
        if dup:
            continue
        rule["status"] = "draft"
        rules.append(rule)
        existing_ids.add(str(rule["id"]))
        added += 1
    kb["rules"] = rules
    feedback.save_knowledge(forge_root, kb)
    return {"added": added, "total_rules": len(rules)}


def audit_legacy(
    project: Path,
    *,
    forge_root: Optional[Path] = None,
    write_docs: bool = True,
    merge_kb: bool = True,
    docs_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Run full audit. `project` = path to legacy tree (any folder with .luau).
    Docs/rules written under forge_root (Quality Forge repo), not inside legacy.
    """
    project = project.resolve()
    forge_root = (forge_root or Path(__file__).resolve().parents[1]).resolve()
    docs = docs_dir or (forge_root / "docs")
    out_dir = forge_root / ".forge" / "legacy_audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    modules = decompose_project(project)
    pitfalls = find_pitfalls(project)
    # next rule id from forge KB
    start_id = 1
    try:
        from . import feedback

        kb = feedback.load_knowledge(forge_root)
        for r in kb.get("rules") or []:
            m = re.match(r"R(\d+)$", str((r or {}).get("id") or ""))
            if m:
                start_id = max(start_id, int(m.group(1)) + 1)
    except Exception:
        pass
    draft_rules = pitfalls_to_draft_rules(pitfalls, start_id=start_id)

    arch_md = render_architecture_md(modules, project=project)
    pit_md = render_pitfalls_md(pitfalls, project=project)

    arch_path = docs / "LEGACY_ARCHITECTURE.md"
    pit_path = docs / "LEGACY_PITFALLS.md"
    rules_path = out_dir / "draft_rules.json"
    summary_path = out_dir / "summary.json"

    if write_docs:
        docs.mkdir(parents=True, exist_ok=True)
        arch_path.write_text(arch_md, encoding="utf-8")
        pit_path.write_text(pit_md, encoding="utf-8")
        rules_path.write_text(
            json.dumps({"version": 1, "rules": draft_rules, "project": str(project)}, indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )

    kb_report = {"added": 0}
    if merge_kb and draft_rules:
        kb_report = merge_draft_rules_into_kb(forge_root, draft_rules)

    summary = {
        "ok": True,
        "project": str(project),
        "forge_root": str(forge_root),
        "modules": len(modules),
        "functions": sum(len(m.functions) for m in modules),
        "pitfalls": len(pitfalls),
        "by_severity": {
            "crit": sum(1 for p in pitfalls if p.severity == "crit"),
            "high": sum(1 for p in pitfalls if p.severity == "high"),
            "med": sum(1 for p in pitfalls if p.severity == "med"),
        },
        "draft_rules": len(draft_rules),
        "kb_merge": kb_report,
        "architecture": str(arch_path) if write_docs else None,
        "pitfalls_md": str(pit_path) if write_docs else None,
        "draft_rules_json": str(rules_path) if write_docs else None,
        "at": now_iso(),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary["summary_json"] = str(summary_path)
    # lightweight machine lists for tests
    summary["_modules"] = [asdict(m) for m in modules]
    summary["_pitfalls"] = [asdict(p) for p in pitfalls]
    summary["_draft_rules"] = draft_rules
    return summary
