"""A16.0 — pre-flight checklist printed when launching --ui (and /api/checklist)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DEFAULT = Path(__file__).resolve().parents[1]


def _ollama_ok(timeout: float = 1.2) -> Dict[str, Any]:
    try:
        from . import ollama_client

        ok = ollama_client.ping(timeout=int(max(1, timeout)))
        models = ollama_client.list_models() if ok else []
        want = ("14b", "7b", "qwen")
        has_coder = any(any(t in m.lower() for t in want) for m in models)
        return {
            "ok": bool(ok),
            "models": models[:12],
            "has_coder_hint": has_coder,
            "detail": f"{len(models)} model(s)" if ok else "unreachable",
        }
    except Exception as e:
        return {"ok": False, "models": [], "has_coder_hint": False, "detail": str(e)}


def _skeletons_ok(root: Path) -> Dict[str, Any]:
    reg = root / "skeletons" / "registry.json"
    if not reg.is_file():
        return {"ok": False, "detail": "skeletons/registry.json missing", "count": 0}
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
        arches = list((data.get("archetypes") or {}).keys())
        return {"ok": len(arches) >= 4, "detail": ", ".join(arches[:8]), "count": len(arches)}
    except json.JSONDecodeError as e:
        return {"ok": False, "detail": f"corrupt registry: {e}", "count": 0}


def _assets_ok(root: Path) -> Dict[str, Any]:
    catalog = root / "assets" / "catalog" / "assets.json"
    models_dir = root / "assets" / "models"
    n_files = 0
    if models_dir.is_dir():
        n_files = sum(1 for p in models_dir.rglob("*") if p.is_file() and p.suffix.lower() in {
            ".glb", ".gltf", ".ldr", ".fbx", ".obj",
        })
    if not catalog.is_file():
        return {
            "ok": False,
            "detail": f"catalog missing (models on disk: {n_files}) - run --scan-assets",
            "count": 0,
            "models_on_disk": n_files,
        }
    try:
        data = json.loads(catalog.read_text(encoding="utf-8"))
        items = data.get("assets") if isinstance(data.get("assets"), list) else []
        ids_field = data.get("ids") if isinstance(data.get("ids"), list) else []
        count = int(data.get("count") or len(items) or len(ids_field) or 0)
        ids = [str(x) for x in ids_field[:8]] or [
            str(a.get("id") or a.get("name") or "?")
            for a in items[:8]
            if isinstance(a, dict)
        ]
        # Catalog file present = scanned. Warn if disk has models but catalog empty.
        stale = n_files > 0 and count == 0
        return {
            "ok": not stale,
            "detail": (
                ", ".join(ids)
                if ids
                else ("empty (OK - add .glb then --scan-assets)" if n_files == 0 else "STALE - rescan")
            ),
            "count": count,
            "models_on_disk": n_files,
        }
    except json.JSONDecodeError as e:
        return {"ok": False, "detail": f"corrupt catalog: {e}", "count": 0, "models_on_disk": n_files}


def _rules_ok(root: Path) -> Dict[str, Any]:
    from . import feedback

    rules = feedback.load_active_rules(root)
    ids = [str(r.get("id")) for r in rules]
    crit = {"R001", "R004", "R006"}
    have = crit & set(ids)
    return {
        "ok": len(have) >= 3,
        "detail": ", ".join(ids) if ids else "(none active)",
        "count": len(ids),
        "critical": sorted(have),
        "missing_critical": sorted(crit - have),
    }


def _token_economy_ok() -> Dict[str, Any]:
    try:
        from . import llm_backends

        return {
            "ok": True,
            "detail": (
                f"ctx={llm_backends.LOCAL_NUM_CTX} "
                f"prompt<={llm_backends.HARD_PROMPT_TOKENS_14B}/{llm_backends.HARD_PROMPT_TOKENS_7B} "
                f"predict={llm_backends.DEFAULT_NUM_PREDICT}/diff={llm_backends.DIFF_NUM_PREDICT}"
            ),
            "num_predict": llm_backends.DEFAULT_NUM_PREDICT,
            "num_predict_diff": llm_backends.DIFF_NUM_PREDICT,
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}


def build_checklist(root: Optional[Path] = None) -> Dict[str, Any]:
    r = root or ROOT_DEFAULT
    checks = {
        "ollama": _ollama_ok(),
        "skeletons": _skeletons_ok(r),
        "assets": _assets_ok(r),
        "rules": _rules_ok(r),
        "token_economy": _token_economy_ok(),
    }
    ready = all(bool(v.get("ok")) for v in checks.values())
    # Ollama down is warn-not-block for UI (stub still works)
    hard = all(
        bool(checks[k].get("ok")) for k in ("skeletons", "rules", "token_economy")
    )
    return {
        "ready": ready,
        "ready_for_ui": hard,
        "checks": checks,
        "hints": _hints(checks),
    }


def _hints(checks: Dict[str, Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    if not checks["ollama"].get("ok"):
        out.append("Start Ollama: ollama serve && ollama pull qwen2.5-coder:14b-4k")
    elif not checks["ollama"].get("has_coder_hint"):
        out.append("Pull coder model: ollama pull qwen2.5-coder:14b-4k (and 7b-2k for repair)")
    if not checks["skeletons"].get("ok"):
        out.append("Restore skeletons/registry.json from repo")
    if not checks["assets"].get("ok"):
        out.append("Drop .glb into assets/models/ then: python -u run.py --scan-assets")
    if checks["assets"].get("models_on_disk") and not checks["assets"].get("count"):
        out.append("Models on disk but catalog empty - run --scan-assets")
    if not checks["rules"].get("ok"):
        miss = checks["rules"].get("missing_critical") or []
        out.append(f"Activate critical rules: python -u run.py --rules-activate {' '.join(miss)}")
    return out


def print_checklist(root: Optional[Path] = None) -> Dict[str, Any]:
    report = build_checklist(root)
    checks = report["checks"]
    print()
    print("=" * 60)
    print("Quality Forge - Launch Checklist (A16)")
    print("=" * 60)

    def row(label: str, key: str) -> None:
        c = checks[key]
        mark = "OK" if c.get("ok") else "!!"
        print(f"  [{mark}] {label}: {c.get('detail')}")

    row("Ollama", "ollama")
    row("Skeletons", "skeletons")
    row("Assets catalog", "assets")
    row("Validator rules (active)", "rules")
    row("Token economy (A15)", "token_economy")
    if report.get("hints"):
        print("  Hints:")
        for h in report["hints"]:
            print(f"    - {h}")
    status = "READY" if report.get("ready") else ("UI OK (Ollama optional)" if report.get("ready_for_ui") else "NOT READY")
    print(f"  -> {status}")
    print("=" * 60)
    print()
    return report
