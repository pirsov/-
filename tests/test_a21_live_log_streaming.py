#!/usr/bin/env python3
"""A21.0 — live log streaming: append+flush mirror, no full rewrite per line."""
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import run_hub


class TestMirroredLogAppend(unittest.TestCase):
    def test_write_mirrored_log_line_appends_and_flushes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            stamped = root / "stamp.log"
            latest = root / "latest.log"
            with stamped.open("w", encoding="utf-8") as logf, latest.open(
                "a", encoding="utf-8"
            ) as latestf:
                run_hub._write_mirrored_log_line(logf, latestf, "[T1] -> @coder\n")
                # UI poll mid-run must already see the line
                self.assertIn("[T1] -> @coder", latest.read_text(encoding="utf-8"))
                run_hub._write_mirrored_log_line(
                    logf, latestf, "   wrote src/Server/Foo.luau\n"
                )
                run_hub._write_mirrored_log_line(
                    logf, latestf, "  VALIDATOR PASS [Foo.luau]\n"
                )

            stamped_text = stamped.read_text(encoding="utf-8")
            latest_text = latest.read_text(encoding="utf-8")
            self.assertEqual(stamped_text, latest_text)
            self.assertEqual(latest_text.count("\n"), 3)
            self.assertIn("wrote src/Server/Foo.luau", latest_text)
            self.assertIn("VALIDATOR PASS", latest_text)

    def test_append_does_not_call_path_write_text(self):
        """Regression: mirroring must not Path.write_text the whole log each line."""
        buf_log = io.StringIO()
        buf_latest = io.StringIO()
        with patch.object(Path, "write_text", side_effect=AssertionError("no rewrite")):
            run_hub._write_mirrored_log_line(buf_log, buf_latest, "alpha\n")
            run_hub._write_mirrored_log_line(buf_log, buf_latest, "beta\n")
        self.assertEqual(buf_log.getvalue(), "alpha\nbeta\n")
        self.assertEqual(buf_latest.getvalue(), "alpha\nbeta\n")

    def test_run_py_forces_line_buffering(self):
        src = Path(__file__).resolve().parents[1] / "run.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("reconfigure(line_buffering=True)", text)
        self.assertIn("line_buffering=True", text)

    def test_ui_log_poll_has_no_short_abort(self):
        app = (Path(__file__).resolve().parents[1] / "ui" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("setInterval", app)
        self.assertIn("/api/logs", app)
        # Poll waits for fetch; must not AbortSignal / short timeout on logs
        self.assertNotRegex(app, r"AbortSignal\.timeout\s*\(\s*\d{1,4}\s*\)")
        self.assertIn("logPollTimer = setInterval", app)
        self.assertRegex(app, r"logPollTimer = setInterval\([\s\S]*?,\s*2000\)")


if __name__ == "__main__":
    unittest.main()
