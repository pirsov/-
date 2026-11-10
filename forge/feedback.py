"""HITL feedback loop — learn JSON validator rules from human y/n (A6.3).

Yes  → closed_verified + contracts/golden/<plugin>.json
No   → broken_by_user + draft JSON rule; FORGE_RULES_AUTO=1 dry-runs on golden → active|draft
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import state_hub

KB_NAME = "knowledge_base.json"
GOLDEN_DIR = "contracts/golden"
ALLOWED_CHECK_TYPES = frozenset(
    {"forbid_regex", "require_regex", "forbid_substr", "require_substr"}
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def kb_path(root: Path) -> Path:
    return root / KB_NAME


def golden_dir(root: Path) -> Path:
    return root / GOLDEN_DIR


def rules_auto_enabled() -> bool:
    v = (os.environ.get("FORGE_RULES_AUTO") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def load_knowledge(root: Path) -> Dict[str, Any]:
    p = kb_path(root)
    if not p.is_file():
        return {"version": 1, "rules": [], "plugins": {}, "updated_at": now_iso()}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "rules": [], "plugins": {}, "corrupt": True, "updated_at": now_iso()}
    if not isinstance(data, dict):
        return {"version": 1, "rules": [], "plugins": {}}
    data.setdefault("version", 1)
    data.setdefault("rules", [])
    data.setdefault("plugins", {})
    return data


def save_knowledge(root: Path, data: Dict[str, Any]) -> None:
    data["updated_at"] = now_iso()
    kb_path(root).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def next_rule_id(kb: Dict[str, Any]) -> str:
    n = 1
    for r in kb.get("rules") or []:
        rid = str(r.get("id") or "")
        m = re.match(r"R(\d+)$", rid)
        if m:
            n = max(n, int(m.group(1)) + 1)
    return f"R{n:03d}"


def _safe_plugin_name(plugin: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in plugin) or "plugin"


def find_contract_snapshot(root: Path, plugin: str) -> Optional[Dict[str, Any]]:
    """Load contract snapshot from contracts/ or state.done."""
    candidates = [
        root / "contracts" / f"{_safe_plugin_name(plugin)}.json",
        root / "contracts" / f"{plugin}.json",
    ]
    for p in candidates:
        if p.is_file():
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            snap = payload.get("contract_snapshot") if isinstance(payload, dict) else None
            if isinstance(snap, dict):
                return snap
            if isinstance(payload, dict) and payload.get("name"):
                return payload
    state = state_hub.load_state(root)
    for entry in state.get("done") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("plugin") != plugin:
            continue
        snap = entry.get("contract_snapshot")
        if isinstance(snap, dict):
            return snap
        ref = entry.get("contract_ref")
        if ref and (root / ref).is_file():
            try:
                payload = json.loads((root / ref).read_text(encoding="utf-8"))
                s2 = payload.get("contract_snapshot")
                if isinstance(s2, dict):
                    return s2
            except json.JSONDecodeError:
                pass
    return {
        "name": plugin,
        "purpose": f"HITL verified {plugin}",
        "verified_at": now_iso(),
    }


def copy_golden(root: Path, plugin: str, snapshot: Optional[Dict[str, Any]] = None) -> str:
    golden_dir(root).mkdir(parents=True, exist_ok=True)
    snap = snapshot or find_contract_snapshot(root, plugin) or {"name": plugin}
    rel = f"{GOLDEN_DIR}/{_safe_plugin_name(plugin)}.json"
    payload = {
        "plugin": plugin,
        "golden_at": now_iso(),
        "contract_snapshot": snap,
    }
    (root / rel).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rel


def validate_rule_schema(rule: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errs: List[str] = []
    if not rule.get("id"):
        errs.append("missing id")
    checks = rule.get("checks")
    if not isinstance(checks, list) or not checks:
        errs.append("checks must be non-empty list")
        return False, errs
    if len(checks) > 3:
        errs.append("max 3 checks per rule (quota)")
    for i, c in enumerate(checks):
        if not isinstance(c, dict):
            errs.append(f"check[{i}] not object")
            continue
        ctype = c.get("type")
        if ctype not in ALLOWED_CHECK_TYPES:
            errs.append(f"check[{i}] type not allowed: {ctype}")
        if ctype in {"forbid_regex", "require_regex"} and not c.get("pattern"):
            errs.append(f"check[{i}] missing pattern")
        if ctype in {"forbid_substr", "require_substr"} and not c.get("text"):
            errs.append(f"check[{i}] missing text")
        # Reject dangerous regex constructs (rough)
        pat = str(c.get("pattern") or "")
        if "(?P<" in pat or pat.count("(") > 20:
            errs.append(f"check[{i}] pattern too complex")
    match = rule.get("match") or {}
    if match and not isinstance(match, dict):
        errs.append("match must be object")
    return len(errs) == 0, errs


def draft_rule_from_comment(
    *,
    plugin: str,
    comment: str,
    files: Optional[List[str]] = None,
    rule_id: str = "R000",
) -> Dict[str, Any]:
    """
    Deterministic heuristic draft (no LLM required).
    Cloud/7B can later refine; schema stays JSON-only.
    """
    text = (comment or "").strip()
    files = list(files or [])
    checks: List[Dict[str, Any]] = []
    lower = text.lower()

    # Common horror/runner regressions hinted in comments
    if "besttime" in lower.replace(" ", "") or "best time" in lower:
        if "сброс" in lower or "reset" in lower or "0" in text:
            checks.append(
                {
                    "type": "forbid_regex",
                    "pattern": r'SetAttribute\(\s*["\']BestTime["\']\s*,\s*0\s*\)',
                    "msg": f"HITL: do not zero BestTime on death — {text[:80]}",
                }
            )
        checks.append(
            {
                "type": "require_regex",
                "pattern": r"BestTime",
                "msg": f"HITL: BestTime must remain in plugin — {text[:80]}",
            }
        )
    if "coinscollected" in lower.replace(" ", "") or "coins collected" in lower:
        checks.append(
            {
                "type": "forbid_regex",
                "pattern": r"Remotes\.CoinsCollected\b",
                "msg": f"HITL: CoinsCollected remote forbidden — {text[:80]}",
            }
        )
    if "character:getattribute" in lower.replace(" ", "") or "character getattribute" in lower:
        checks.append(
            {
                "type": "forbid_regex",
                "pattern": r"char(?:acter)?\s*:\s*GetAttribute",
                "msg": f"HITL: use player:GetAttribute — {text[:80]}",
            }
        )
    if not checks:
        # Generic: require a distinctive token from comment (quoted or CamelCase)
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", text)
        token = tokens[0] if tokens else "TODO"
        checks.append(
            {
                "type": "forbid_substr",
                "text": "___HITL_PLACEHOLDER_NEVER___",
                "msg": f"HITL note recorded ({token}): {text[:120]}",
            }
        )
        # Also require human keyword presence reminder via require on a safe always-true-ish:
        # use require_substr of empty skip — instead store comment-only advisory require on file existence
        checks = [
            {
                "type": "forbid_substr",
                "text": f"__HITL_BAN_{token[:24]}__",
                "msg": f"HITL: {text[:140]}",
            }
        ]

    checks = checks[:3]
    rule = {
        "id": rule_id,
        "source": "hitl_n",
        "plugin": plugin,
        "human_comment": text[:500],
        "match": {"files": files or _default_files_for_plugin(plugin)},
        "checks": checks,
        "status": "draft",
        "created_at": now_iso(),
    }
    return rule


def _default_files_for_plugin(plugin: str) -> List[str]:
    mapping = {
        "game1.player_data": ["PlayerData.server.luau"],
        "game1.checkpoints": ["Checkpoints.server.luau"],
        "game1.hud": ["HUD.client.luau"],
        "game1.coins": ["Coins.server.luau"],
        "game1.generator": ["Generator.server.luau"],
        "game1.effects": ["Effects.client.luau"],
        "game1.horror_fog": ["HorrorFog.server.luau"],
    }
    return mapping.get(plugin, [])


def apply_checks_to_text(content: str, checks: List[Dict[str, Any]], *, rule_id: str = "") -> List[str]:
    errors: List[str] = []
    for c in checks:
        ctype = c.get("type")
        msg = c.get("msg") or f"rule {rule_id} failed"
        prefix = f"[{rule_id}] " if rule_id else ""
        if ctype == "forbid_regex":
            try:
                if re.search(str(c.get("pattern") or ""), content):
                    errors.append(prefix + str(msg))
            except re.error as e:
                errors.append(f"{prefix}invalid regex: {e}")
        elif ctype == "require_regex":
            try:
                if not re.search(str(c.get("pattern") or ""), content):
                    errors.append(prefix + str(msg))
            except re.error as e:
                errors.append(f"{prefix}invalid regex: {e}")
        elif ctype == "forbid_substr":
            text = str(c.get("text") or "")
            if text and text in content:
                errors.append(prefix + str(msg))
        elif ctype == "require_substr":
            text = str(c.get("text") or "")
            if text and text not in content:
                errors.append(prefix + str(msg))
    return errors


def rule_matches_file(rule: Dict[str, Any], path: Path) -> bool:
    match = rule.get("match") or {}
    files = match.get("files") if isinstance(match, dict) else None
    if not files:
        return True
    name = path.name
    return any(str(f) == name or name.endswith(str(f)) or str(f) in str(path) for f in files)


def load_active_rules(root: Path) -> List[Dict[str, Any]]:
    kb = load_knowledge(root)
    return [r for r in (kb.get("rules") or []) if isinstance(r, dict) and r.get("status") == "active"]


def apply_rules_to_file(root: Path, path: Path, content: str) -> List[str]:
    errors: List[str] = []
    for rule in load_active_rules(root):
        if not rule_matches_file(rule, path):
            continue
        errors.extend(apply_checks_to_text(content, rule.get("checks") or [], rule_id=str(rule.get("id") or "")))
    return errors


def dry_run_rule_on_golden(root: Path, rule: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Green if rule does NOT fire on any golden contract *source* samples.
    Golden JSON holds contract snapshots (metadata), not Luau — so we also
    scan src/ files matching rule.match.files when present. If no files exist,
    treat as green (nothing to regress against).
    """
    errs: List[str] = []
    match = rule.get("match") or {}
    files = list((match.get("files") if isinstance(match, dict) else None) or [])
    scanned = 0
    # Prefer live src matches
    for p in root.rglob("*.luau"):
        if files and not rule_matches_file(rule, p):
            continue
        if not files and GOLDEN_DIR not in str(p):
            # without file filter, only scan if golden has companion sample — skip broad
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except OSError:
            continue
        scanned += 1
        hit = apply_checks_to_text(content, rule.get("checks") or [], rule_id=str(rule.get("id")))
        # For dry-run: forbid_* firing on golden/current good tree = red (would break good code)
        # require_* failing on good tree = also red
        if hit:
            errs.extend(f"{p.name}: {e}" for e in hit)

    # If rule only has advisory forbid_substr of synthetic token, never present → green
    if scanned == 0:
        return True, []
    return len(errs) == 0, errs


def maybe_auto_activate(root: Path, rule: Dict[str, Any]) -> Dict[str, Any]:
    """If FORGE_RULES_AUTO and dry-run green → status active; else stay draft."""
    report = {"rule_id": rule.get("id"), "auto": rules_auto_enabled(), "activated": False, "dry_ok": False, "errors": []}
    if not rules_auto_enabled():
        report["reason"] = "FORGE_RULES_AUTO off"
        return report
    ok, errs = dry_run_rule_on_golden(root, rule)
    report["dry_ok"] = ok
    report["errors"] = errs[:12]
    if ok:
        rule["status"] = "active"
        rule["activated_at"] = now_iso()
        report["activated"] = True
        report["reason"] = "dry-run green → active"
    else:
        rule["status"] = "draft"
        report["reason"] = "dry-run red → draft awaiting review"
    return report


def set_plugin_status(root: Path, plugin: str, status: str, **extra: Any) -> None:
    kb = load_knowledge(root)
    plugins = kb.setdefault("plugins", {})
    entry = plugins.get(plugin) if isinstance(plugins.get(plugin), dict) else {}
    entry.update({"status": status, "updated_at": now_iso(), **extra})
    plugins[plugin] = entry
    save_knowledge(root, kb)

    state = state_hub.load_state(root)
    state.setdefault("knowledge_ref", KB_NAME)
    found = None
    for d in state.get("done") or []:
        if isinstance(d, dict) and d.get("plugin") == plugin:
            found = d
            break
    if found is None:
        found = {"plugin": plugin}
        state.setdefault("done", []).append(found)
    found["status"] = status
    found["hitl_at"] = now_iso()
    for k, v in extra.items():
        if k in {"golden_ref", "note", "broken_reason", "rule_ids"}:
            found[k] = v
    state_hub.save_state(root, state)


def on_yes(root: Path, plugin: str, note: str = "") -> Dict[str, Any]:
    snap = find_contract_snapshot(root, plugin)
    golden_rel = copy_golden(root, plugin, snap)
    set_plugin_status(
        root,
        plugin,
        "closed_verified",
        golden_ref=golden_rel,
        note=note or "human yes",
    )
    return {
        "verdict": "yes",
        "plugin": plugin,
        "status": "closed_verified",
        "golden_ref": golden_rel,
        "note": note,
    }


def on_no(
    root: Path,
    plugin: str,
    note: str,
    *,
    files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    kb = load_knowledge(root)
    rid = next_rule_id(kb)
    rule = draft_rule_from_comment(plugin=plugin, comment=note, files=files, rule_id=rid)
    ok_schema, schema_errs = validate_rule_schema(rule)
    if not ok_schema:
        rule["status"] = "draft"
        rule["schema_errors"] = schema_errs
    auto_report = maybe_auto_activate(root, rule) if ok_schema else {"activated": False, "reason": "schema invalid", "errors": schema_errs}
    kb.setdefault("rules", []).append(rule)
    save_knowledge(root, kb)
    set_plugin_status(
        root,
        plugin,
        "broken_by_user",
        note=note,
        broken_reason=note[:300],
        rule_ids=[rid],
    )
    state_hub.record_task_status(
        root,
        f"HITL-{plugin}",
        status="failed",
        note=f"broken_by_user: {note[:160]}",
        backend="hitl",
    )
    return {
        "verdict": "no",
        "plugin": plugin,
        "status": "broken_by_user",
        "rule": rule,
        "auto": auto_report,
    }


def submit_verdict(
    root: Path,
    plugin: str,
    verdict: str,
    note: str = "",
    *,
    files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    v = (verdict or "").strip().lower()
    if v in {"y", "yes", "да", "1", "true"}:
        return on_yes(root, plugin, note=note)
    if v in {"n", "no", "нет", "0", "false"}:
        if not (note or "").strip():
            note = "(no detail provided)"
        return on_no(root, plugin, note=note, files=files)
    raise ValueError(f"verdict must be y/n, got {verdict!r}")


def list_rules(root: Path, *, status: Optional[str] = None) -> List[Dict[str, Any]]:
    kb = load_knowledge(root)
    rules = [r for r in (kb.get("rules") or []) if isinstance(r, dict)]
    if status:
        rules = [r for r in rules if r.get("status") == status]
    return rules


def activate_rule(root: Path, rule_id: str, *, force: bool = False) -> Dict[str, Any]:
    kb = load_knowledge(root)
    for rule in kb.get("rules") or []:
        if not isinstance(rule, dict) or rule.get("id") != rule_id:
            continue
        ok_schema, errs = validate_rule_schema(rule)
        if not ok_schema:
            return {"ok": False, "errors": errs}
        if not force:
            dry_ok, dry_errs = dry_run_rule_on_golden(root, rule)
            if not dry_ok:
                return {"ok": False, "errors": dry_errs, "reason": "dry-run red"}
        rule["status"] = "active"
        rule["activated_at"] = now_iso()
        save_knowledge(root, kb)
        return {"ok": True, "rule_id": rule_id, "status": "active"}
    return {"ok": False, "errors": [f"rule {rule_id} not found"]}


def format_rules_for_prompt(rules: List[Dict[str, Any]], *, max_chars: int = 1200) -> str:
    lines: List[str] = []
    for r in rules:
        if r.get("status") != "active":
            continue
        lines.append(f"- {r.get('id')}: {r.get('human_comment', '')[:100]}")
        for c in (r.get("checks") or [])[:3]:
            lines.append(f"    {c.get('type')}: {c.get('pattern') or c.get('text')}")
    text = "\n".join(lines)
    return text[:max_chars]
