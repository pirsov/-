"""Minimal Quality Forge control UI: projects, skills, DeepSeek, week run, smoke."""
from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

from . import deepseek, progress_hub, projects_hub, run_hub, skills_hub

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quieter
        print(f"[ui] {args[0]}")

    def _json(self, code: int, payload: Any) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in {"/", "/index.html"}:
            self._file(UI_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path == "/app.js":
            self._file(UI_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if path == "/styles.css":
            self._file(UI_DIR / "styles.css", "text/css; charset=utf-8")
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
            qs = urllib.parse.parse_qs(parsed.query)
            rel = (qs.get("path") or [""])[0]
            try:
                self._json(200, run_hub.read_code_file(rel, ROOT))
            except Exception as e:
                self._json(400, {"error": f"{type(e).__name__}: {e}"})
            return
        if path == "/api/smoke/questions":
            qs = urllib.parse.parse_qs(parsed.query)
            pid = (qs.get("project") or ["game1"])[0]
            self._json(200, deepseek.smoke_questionnaire(project_id=pid))
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json()
        try:
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
                    # still allow fallback TZ without key
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
                            skills_hub.promote_compact(sid, ROOT, smoke_ok=True, notes="ui smoke")
                        except FileNotFoundError:
                            pass
                progress_hub.mark(ROOT, smoke_done=True)
                self._json(200, {"ok": True, "saved": str(path_out), "progress": progress_hub.snapshot(ROOT)})
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
            # Browser refresh / tab close mid-transfer — ignore.
            return


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Quality Forge UI http://{host}:{port}")
    print("  projects / skills / TZ / week run / smoke")
    httpd.serve_forever()
