#!/usr/bin/env python3
"""A18.1 — /api/logs tail + current_task on status_snapshot."""
from __future__ import annotations

import json
import socket
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from forge import api_hub, run_hub


def _reset_run_hub() -> None:
    run_hub._stop_event.clear()
    with run_hub._lock:
        run_hub._state.update(
            {
                "status": "idle",
                "started_at": None,
                "ended_at": None,
                "exit_code": None,
                "pid": None,
                "log_path": None,
                "report": {},
                "mode": None,
                "waiting_reason": None,
                "waiting_detail": None,
                "loop_cycle": 0,
                "loop_max": 0,
                "stop_requested": False,
            }
        )


def _seed_root(root: Path) -> None:
    (root / "state.json").write_text(
        json.dumps(
            {
                "pulse": {"cycle": 1},
                "done": [{"plugin": "game1.hud", "status": "done"}],
                "task_queue": [
                    {"id": "T2", "status": "in_progress", "title": "DataStore PlayerSave"},
                    {"id": "T3", "status": "ready", "title": "networking glue"},
                ],
                "open_questions": [],
            }
        ),
        encoding="utf-8",
    )
    (root / "knowledge_base.json").write_text(
        json.dumps({"rules": [], "plugins": {}}),
        encoding="utf-8",
    )


class TestAgentLogs(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        _reset_run_hub()

    def test_agent_logs_tails_last_lines(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / ".forge" / "ui_run"
            run_dir.mkdir(parents=True)
            log_path = run_dir / "loop24-test.log"
            lines = [f"line-{i}" for i in range(1, 121)]
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with run_hub._lock:
                run_hub._state["log_path"] = str(log_path)

            out = api_hub.agent_logs(root, lines=80)
            self.assertTrue(out["ok"])
            self.assertEqual(out["count"], 80)
            self.assertEqual(out["total_lines"], 120)
            self.assertEqual(out["lines"][0], "line-41")
            self.assertEqual(out["lines"][-1], "line-120")
            self.assertIn("line-120", out["text"])
            self.assertNotIn("line-1\n", out["text"] + "\n")

    def test_agent_logs_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = api_hub.agent_logs(root, lines=50)
            self.assertTrue(out["ok"])
            self.assertEqual(out["count"], 0)
            self.assertEqual(out["text"], "")
            self.assertEqual(out["lines"], [])


class TestCurrentTask(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        _reset_run_hub()

    def test_status_snapshot_includes_current_task(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            snap = api_hub.status_snapshot(root)
            self.assertTrue(snap["ok"])
            self.assertEqual(snap["current_task"], "T2: DataStore PlayerSave")

    def test_derive_current_task_from_heartbeat(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "pulse": {"cycle": 2},
                        "done": [],
                        "task_queue": [
                            {"id": "W1.5", "status": "ready", "title": "Fog volume"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "knowledge_base.json").write_text(
                json.dumps({"rules": [], "plugins": {}}), encoding="utf-8"
            )
            hb = root / ".forge" / "state"
            hb.mkdir(parents=True)
            (hb / "heartbeat.json").write_text(
                json.dumps({"status": "running", "task": "W1.5"}),
                encoding="utf-8",
            )
            label = api_hub.derive_current_task(root)
            self.assertEqual(label, "W1.5: Fog volume")

    def test_waiting_human_hitl_label(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "state.json").write_text(
                json.dumps({"pulse": {"cycle": 0}, "done": [], "task_queue": []}),
                encoding="utf-8",
            )
            (root / "knowledge_base.json").write_text(
                json.dumps({"rules": [], "plugins": {}}), encoding="utf-8"
            )
            run_hub.set_waiting_human(
                reason="verify_plugin", detail={"plugin": "game1.hud"}
            )
            snap = api_hub.status_snapshot(root)
            self.assertTrue(snap["waiting_human"])
            self.assertEqual(snap["current_task"], "HITL: game1.hud")


class TestUiServerLogsRoute(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        _reset_run_hub()

    def test_get_api_logs_and_status_current_task(self):
        from forge import ui_server

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            run_dir = root / ".forge" / "ui_run"
            run_dir.mkdir(parents=True)
            log_path = run_dir / "latest.log"
            log_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
            with run_hub._lock:
                run_hub._state["log_path"] = str(log_path)

            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()

            with patch.object(ui_server, "ROOT", root):
                server = ui_server.ThreadingHTTPServer(
                    ("127.0.0.1", port), ui_server.Handler
                )
                t = threading.Thread(target=server.serve_forever, daemon=True)
                t.start()
                try:
                    conn = HTTPConnection("127.0.0.1", port, timeout=5)
                    conn.request("GET", "/api/logs?lines=50")
                    res = conn.getresponse()
                    body = json.loads(res.read().decode("utf-8"))
                    self.assertEqual(res.status, 200)
                    self.assertTrue(body.get("ok"))
                    self.assertEqual(body.get("lines"), ["alpha", "beta", "gamma"])

                    conn.request("GET", "/api/status")
                    res2 = conn.getresponse()
                    body2 = json.loads(res2.read().decode("utf-8"))
                    self.assertEqual(res2.status, 200)
                    self.assertEqual(body2.get("current_task"), "T2: DataStore PlayerSave")
                    self.assertEqual(
                        (body2.get("snapshot") or {}).get("current_task"),
                        "T2: DataStore PlayerSave",
                    )

                    conn.request("GET", "/api/status_snapshot")
                    res3 = conn.getresponse()
                    body3 = json.loads(res3.read().decode("utf-8"))
                    self.assertEqual(res3.status, 200)
                    self.assertEqual(body3.get("current_task"), "T2: DataStore PlayerSave")
                    conn.close()
                finally:
                    server.shutdown()


class TestDarkCssCacheBust(unittest.TestCase):
    def test_index_links_versioned_css_js(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/styles.css?v=a18.1"', html)
        self.assertIn('src="/app.js?v=a18.1"', html)
        css = (root / "ui" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("--bg: #0f172a", css)
        self.assertIn("--panel: #1e293b", css)
        self.assertNotRegex(css, r"--bg:\s*#(f|e|d|c)[0-9a-f]{5}", "no light/brown bg")


if __name__ == "__main__":
    unittest.main()
