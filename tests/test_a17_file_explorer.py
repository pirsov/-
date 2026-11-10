#!/usr/bin/env python3
"""A17.0 — /api/files + /api/file (path traversal rejected)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from forge import api_hub


def _seed(root: Path) -> None:
    (root / "src" / "shared" / "Content").mkdir(parents=True)
    (root / "src" / "shared" / "Content" / "LevelConfig.luau").write_text(
        "-- level\nreturn {}\n", encoding="utf-8"
    )
    (root / "src" / "server" / "Gameplay").mkdir(parents=True)
    (root / "src" / "server" / "Gameplay" / "Coins.server.luau").write_text(
        "print('coins')\n", encoding="utf-8"
    )
    (root / "projects" / "game1" / "src" / "client").mkdir(parents=True)
    (root / "projects" / "game1" / "src" / "client" / "HUD.client.luau").write_text(
        "print('hud')\n", encoding="utf-8"
    )
    (root / ".forge").mkdir(parents=True)
    (root / ".forge" / "active_project.json").write_text(
        json.dumps({"id": "game1"}), encoding="utf-8"
    )
    # decoy outside allowed roots
    (root / "secrets.txt").write_text("TOPSECRET\n", encoding="utf-8")
    (root / "outside").mkdir()
    (root / "outside" / "evil.luau").write_text("bad\n", encoding="utf-8")


class TestListFiles(unittest.TestCase):
    def test_lists_workspace_and_active_project_src(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed(root)
            out = api_hub.list_files(root)
            self.assertTrue(out["ok"])
            files = out["files"]
            self.assertIsInstance(files, list)
            self.assertIn("src/shared/Content/LevelConfig.luau", files)
            self.assertIn("src/server/Gameplay/Coins.server.luau", files)
            self.assertIn("projects/game1/src/client/HUD.client.luau", files)
            self.assertEqual(out["active_project"], "game1")
            self.assertIn("src", out["roots"])
            self.assertIn("projects/game1/src", out["roots"])
            tree = out.get("tree") or []
            self.assertTrue(tree)
            self.assertTrue(any(n.get("name") == "src" and n.get("type") == "dir" for n in tree))
            # must not leak non-src paths
            self.assertFalse(any(f.startswith("secrets") for f in files))
            self.assertFalse(any("outside" in f for f in files))

    def test_without_active_project_only_live_src(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "src").mkdir()
            (root / "src" / "A.luau").write_text("a\n", encoding="utf-8")
            (root / "projects" / "game1" / "src").mkdir(parents=True)
            (root / "projects" / "game1" / "src" / "B.luau").write_text("b\n", encoding="utf-8")
            out = api_hub.list_files(root)
            self.assertEqual(out["files"], ["src/A.luau"])
            self.assertIsNone(out["active_project"])


class TestReadFile(unittest.TestCase):
    def test_reads_allowed_src_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed(root)
            out = api_hub.read_file("src/shared/Content/LevelConfig.luau", root)
            self.assertTrue(out["ok"])
            self.assertIn("level", out["content"])
            self.assertEqual(out["path"], "src/shared/Content/LevelConfig.luau")

    def test_reads_project_src_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed(root)
            out = api_hub.read_file("projects/game1/src/client/HUD.client.luau", root)
            self.assertTrue(out["ok"])
            self.assertIn("hud", out["content"])

    def test_path_traversal_dotdot_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed(root)
            with self.assertRaises(ValueError) as ctx:
                api_hub.read_file("src/../../secrets.txt", root)
            self.assertIn("traversal", str(ctx.exception).lower())

    def test_path_outside_src_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed(root)
            with self.assertRaises(ValueError):
                api_hub.read_file("secrets.txt", root)

    def test_absolute_and_empty_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed(root)
            with self.assertRaises(ValueError):
                api_hub.read_file("", root)
            with self.assertRaises(ValueError):
                api_hub.read_file("/etc/passwd", root)

    def test_missing_file_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed(root)
            with self.assertRaises(FileNotFoundError):
                api_hub.read_file("src/nope.luau", root)


class TestUiServerRoutes(unittest.TestCase):
    """Smoke: Handler GET routes for /api/files and /api/file."""

    def test_handler_routes_exist(self):
        from forge import ui_server

        src = Path(ui_server.__file__).read_text(encoding="utf-8")
        self.assertIn('path == "/api/files"', src)
        self.assertIn('path == "/api/file"', src)
        self.assertIn("api_hub.list_files", src)
        self.assertIn("api_hub.read_file", src)


if __name__ == "__main__":
    unittest.main()
