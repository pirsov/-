"""Minimal Quality Forge control UI: projects, skills, DeepSeek, week run, smoke."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import deepseek, progress_hub, projects_hub, run_hub, skills_hub

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui"

# Health probe cache (avoid stalling UI when Ollama is slow/down).
_health_cache: Dict[str, Any] = {"at": 0.0, "payload": None}
_HEALTH_TTL = 15.0


def _probe_ollama(timeout: float = 1.2) -> Dict[str, Any]:
    url = "http://127.0.0.1:11434/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
        models = [m.get("name") for m in (raw.get("models") or []) if m.get("name")]
        return {"ok": True, "models": models[:24], "count": len(models)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "models": [], "count": 0}


def health_snapshot(*, force: bool = False) -> Dict[str, Any]:
    now = time.time()
    if (
        not force
        and _health_cache["payload"] is not None
        and (now - float(_health_cache["at"])) < _HEALTH_TTL
    ):
        return dict(_health_cache["payload"])
    ollama = _probe_ollama()
    payload = {
        "ok": True,
        "deepseek": deepseek.available(),
        "ollama": ollama,
        "cached_for_s": _HEALTH_TTL,
        "ts": now,
    }
    _health_cache["at"] = now
    _health_cache["payload"] = payload
    return dict(payload)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quieter
        print(f"[ui] {args[0]}")

    def _json(self, code: int, payload: Any) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def _read_json(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        if path in {"/", "/index.html"}:
            self._file(UI_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path == "/app.js":
            self._file(UI_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if path == "/styles.css":
            self._file(UI_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if path == "/api/health":
            force = (qs.get("force") or [""])[0] in {"1", "true", "yes"}
            self._json(200, health_snapshot(force=force))
            return
        if path == "/api/progress":
            smoke_loaded = (qs.get("smoke_loaded") or [""])[0] in {"1", "true", "yes"}
            self._json(200, progress_hub.snapshot(ROOT, smoke_loaded=smoke_loaded))
            return
        if path == "/api/status":
            self._json(
                200,
                {
                    "deepseek": deepseek.available(),
                    "projects": projects_hub.list_projects(ROOT),
                    "compact": skills_hub.list_compact(ROOT),
                    "raw_count": len(skills_hub.list_raw(ROOT)),
                    "run": run_hub.status(),
                    "progress": progress_hub.snapshot(ROOT),
                    "health": health_snapshot(),
                },
            )
            return
        if path == "/api/raw":
            self._json(200, {"raw": skills_hub.list_raw(ROOT)})
            return
        if path == "/api/run/status":
            self._json(200, run_hub.status())
            return
        if path == "/api/run/log":
            self._json(200, {"log": run_hub.full_log(ROOT)})
            return
        if path == "/api/run/files":
            self._json(200, {"files": run_hub.list_code_files(ROOT)})
            return
        if path == "/api/run/file":
            rel = (qs.get("path") or [""])[0]
            try:
                self._json(200, run_hub.read_code_file(rel, ROOT))
            except Exception as e:
                self._json(400, {"error": f"{type(e).__name__}: {e}"})
            return
        if path == "/api/smoke/questions":
            pid = (qs.get("project") or ["game1"])[0]
            self._json(200, deepseek.smoke_questionnaire(project_id=pid))
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json()
        try:
            if path == "/api/progress/skip":
                stage = int(body.get("stage") or 0)
                through = body.get("through")
                undo = bool(body.get("undo"))
                if stage < 1 or stage > 5:
                    self._json(400, {"error": "stage must be 1..5"})
                    return
                progress = progress_hub.skip(
                    ROOT,
                    stage,
                    through=int(through) if through is not None else None,
                    undo=undo,
                )
                self._json(200, {"ok": True, "progress": progress})
                return
            if path == "/api/goal/improve":
                goal = (body.get("goal") or "").strip()
                if not goal:
                    self._json(400, {"error": "goal empty"})
                    return
                pid = body.get("project") or "game1"
                compact = body.get("compact_skills")
                result = deepseek.improve_goal(
                    goal,
                    project_id=pid,
                    compact_skills=compact if isinstance(compact, list) else None,
                )
                self._json(200, {"ok": True, "goal": result["goal"], "skills_hint": result["skills_hint"]})
                return
            if path == "/api/compress":
                raw_id = body.get("raw_id") or ""
                text, dest = skills_hub.compress_raw_to_compact(
                    raw_id, ROOT, max_chars=int(body.get("max_chars") or 1200)
                )
                self._json(200, {"ok": True, "path": str(dest), "chars": len(text), "preview": text[:500]})
                return
            if path == "/api/skills/auto":
                goal = body.get("goal") or "Roblox obstacle course HUD coins checkpoints"
                pid = body.get("project") or "game1"
                result = skills_hub.auto_select_and_compress(
                    goal,
                    ROOT,
                    max_pick=int(body.get("max_pick") or 3),
                    max_chars=int(body.get("max_chars") or 1200),
                    project_id=pid,
                )
                progress_hub.mark(ROOT, skills_done=True)
                self._json(200, {"ok": True, "progress": progress_hub.snapshot(ROOT), **result})
                return
            if path == "/api/activate":
                pid = body.get("project") or "game1"
                projects_hub.activate_project(ROOT, pid)
                progress_hub.mark(ROOT, activated=True)
                self._json(200, {"ok": True, "project": pid, "progress": progress_hub.snapshot(ROOT)})
                return
            if path == "/api/tz":
                pid = body.get("project") or "game1"
                goal = body.get("goal") or "Improve playable obstacle course"
                compact = [c["id"] for c in skills_hub.list_compact(ROOT)]
                meta_p = ROOT / "projects" / pid / "meta.json"
                if meta_p.exists():
                    meta = json.loads(meta_p.read_text(encoding="utf-8"))
                    if meta.get("skills_compact"):
                        compact = list(meta["skills_compact"])
                files = [str(p.relative_to(ROOT)) for p in (ROOT / "projects" / pid).rglob("*.luau")]
                if not deepseek.available():
                    tz = deepseek.horror_coins_tz_fallback(project_id=pid, goal=goal)
                else:
                    tz = deepseek.generate_project_tz(
                        project_id=pid, goal=goal, compact_skills=compact, existing_files=files
                    )
                n_tasks = deepseek.count_tz_tasks(tz)
                out = ROOT / "projects" / pid / "PROJECT_TZ.generated.md"
                out.write_text(tz, encoding="utf-8")
                (ROOT / "PROJECT_TZ.md").write_text(tz, encoding="utf-8")
                (ROOT / "projects" / pid / "PROJECT_TZ.md").write_text(tz, encoding="utf-8")
                if n_tasks >= 5:
                    progress_hub.mark(ROOT, tz_done=True)
                self._json(
                    200,
                    {
                        "ok": True,
                        "path": str(out),
                        "live": "PROJECT_TZ.md",
                        "task_lines": n_tasks,
                        "fits_ctx": n_tasks > 0 and len(tz) < 8000,
                        "preview": tz[:1800],
                        "progress": progress_hub.snapshot(ROOT),
                    },
                )
                return
            if path == "/api/run/start":
                result = run_hub.start_week(
                    ROOT,
                    sleep=float(body.get("sleep") if body.get("sleep") is not None else 0),
                    hitl=str(body.get("hitl") or "y"),
                    max_steps=body.get("max"),
                )
                self._json(200 if result.get("ok") else 409, result)
                return
            if path == "/api/smoke/submit":
                pid = body.get("project") or "game1"
                path_out = projects_hub.save_smoke(ROOT, pid, body)
                if body.get("overall_ok"):
                    for sid in body.get("promote_skills") or [
                        "forge-player-attrs",
                        "forge-luau-touch",
                        "forge-ui-modern",
                        "forge-ui-animation",
                    ]:
                        try:
                            note = body.get("notes") or "ui smoke"
                            skills_hub.promote_compact(sid, ROOT, smoke_ok=True, notes=note)
                        except FileNotFoundError:
                            pass
                progress_hub.mark(ROOT, smoke_done=True)
                saved = {}
                try:
                    saved = json.loads(path_out.read_text(encoding="utf-8"))
                except Exception:
                    saved = {"path": str(path_out)}
                self._json(
                    200,
                    {
                        "ok": True,
                        "saved": str(path_out),
                        "others": saved.get("others") or [],
                        "answers": saved.get("answers") or {},
                        "progress": progress_hub.snapshot(ROOT),
                    },
                )
                return
            if path == "/api/promote":
                sid = body.get("skill_id") or ""
                skills_hub.promote_compact(sid, ROOT, smoke_ok=True, notes=body.get("notes") or "")
                self._json(200, {"ok": True, "skill": sid})
                return
        except Exception as e:
            self._json(500, {"error": f"{type(e).__name__}: {e}"})
            return
        self._json(404, {"error": "not found"})

    def _file(self, path: Path, ctype: str) -> None:
        if not path.exists():
            self._json(404, {"error": f"missing {path.name}"})
            return
        raw = path.read_bytes()
        try:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Quality Forge UI http://{host}:{port}")
    print("  projects / skills / TZ / week run / smoke")
    httpd.serve_forever()
