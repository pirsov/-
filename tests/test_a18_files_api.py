#!/usr/bin/env python3
"""A18.0 — /api/files + /api/file (path traversal + src/projects roots)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import api_hub


def _seed_src(root: Path) -> None:
    (root / "src" / "server").mkdir(parents=True)
    (root / "src" / "client").mkdir(parents=True)
    (root / "src" / "server" / "Main.server.luau").write_text("-- server\n", encoding="utf-8")
    (root / "src" / "client" / "HUD.client.luau").write_text("-- client\n", encoding="utf-8")
    (root / "projects" / "game1" / "src" / "shared").mkdir(parents=True)
    (root / "projects" / "game1" / "src" / "shared" / "Remotes.luau").write_text(
        "return {}\n", encoding="utf-8"
    )
    (root / ".forge").mkdir(parents=True)
    (root / ".forge" / "active_project.json").write_text(
        json.dumps({"id": "game1"}), encoding="utf-8"
    )
    # decoy outside allowed roots
    (root / "secrets.txt").write_text("nope", encoding="utf-8")
    (root / "contracts").mkdir(parents=True, exist_ok=True)
    (root / "contracts" / "evil.luau").write_text("-- no", encoding="utf-8")


class TestListFiles(unittest.TestCase):
    def test_lists_live_and_active_project_src(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_src(root)
            out = api_hub.list_files(root)
            self.assertTrue(out["ok"])
            files = out["files"]
            self.assertIn("src/server/Main.server.luau", files)
            self.assertIn("src/client/HUD.client.luau", files)
            self.assertIn("projects/game1/src/shared/Remotes.luau", files)
            self.assertNotIn("secrets.txt", files)
            self.assertNotIn("contracts/evil.luau", files)
            self.assertEqual(out["active_project"], "game1")
            self.assertIn("src", out["roots"])
            self.assertIn("projects/game1/src", out["roots"])
            self.assertIsInstance(out["tree"], list)
            self.assertTrue(out["tree"])

    def test_tree_nested(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_src(root)
            tree = api_hub.list_files(root)["tree"]
            names = {n["name"] for n in tree}
            self.assertIn("src", names)
            src = next(n for n in tree if n["name"] == "src")
            self.assertEqual(src["type"], "dir")
            child_names = {c["name"] for c in src["children"]}
            self.assertTrue({"server", "client"} & child_names)


class TestReadFile(unittest.TestCase):
    def test_reads_allowed_src(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_src(root)
            out = api_hub.read_file("src/server/Main.server.luau", root)
            self.assertTrue(out["ok"])
            self.assertIn("-- server", out["content"])
            self.assertFalse(out["truncated"])

    def test_reads_project_src(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_src(root)
            out = api_hub.read_file("projects/game1/src/shared/Remotes.luau", root)
            self.assertTrue(out["ok"])
            self.assertIn("return", out["content"])

    def test_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_src(root)
            with self.assertRaises(ValueError):
                api_hub.read_file("../secrets.txt", root)
            with self.assertRaises(ValueError):
                api_hub.read_file("src/../../secrets.txt", root)
            with self.assertRaises(ValueError):
                api_hub.read_file("contracts/evil.luau", root)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_src(root)
            with self.assertRaises(FileNotFoundError):
                api_hub.read_file("src/missing.luau", root)


class TestUiServerFilesRoutes(unittest.TestCase):
    def test_get_api_files_and_file(self):
        from forge import ui_server
        from http.client import HTTPConnection
        import threading

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_src(root)
            # Bind ephemeral port
            import socket

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
                    conn.request("GET", "/api/files")
                    res = conn.getresponse()
                    body = json.loads(res.read().decode("utf-8"))
                    self.assertEqual(res.status, 200)
                    self.assertTrue(body.get("ok"))
                    self.assertIn("src/server/Main.server.luau", body.get("files") or [])

                    conn.request(
                        "GET", "/api/file?path=src/server/Main.server.luau"
                    )
                    res2 = conn.getresponse()
                    body2 = json.loads(res2.read().decode("utf-8"))
                    self.assertEqual(res2.status, 200)
                    self.assertIn("-- server", body2.get("content") or "")

                    conn.request("GET", "/api/file?path=../secrets.txt")
                    res3 = conn.getresponse()
                    self.assertEqual(res3.status, 400)
                    conn.close()
                finally:
                    server.shutdown()


if __name__ == "__main__":
    unittest.main()
