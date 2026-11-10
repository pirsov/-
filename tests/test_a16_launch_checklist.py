#!/usr/bin/env python3
"""A16.0 launch checklist — skeletons/rules/assets/token economy."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestLaunchChecklist(unittest.TestCase):
    def test_repo_checklist_ready_for_ui(self):
        from forge import launch_checklist

        report = launch_checklist.build_checklist(ROOT)
        self.assertIn("checks", report)
        self.assertTrue(report["checks"]["skeletons"]["ok"], report["checks"]["skeletons"])
        self.assertTrue(report["checks"]["rules"]["ok"], report["checks"]["rules"])
        self.assertTrue(report["checks"]["token_economy"]["ok"])
        self.assertTrue(report.get("ready_for_ui"), report)
        # critical trio active
        self.assertEqual(
            set(report["checks"]["rules"]["critical"]),
            {"R001", "R004", "R006"},
        )

    def test_missing_skeletons_not_ok(self):
        from forge import launch_checklist

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "knowledge_base.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "rules": [
                            {"id": "R001", "status": "active"},
                            {"id": "R004", "status": "active"},
                            {"id": "R006", "status": "active"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = launch_checklist.build_checklist(root)
            self.assertFalse(report["checks"]["skeletons"]["ok"])

    def test_start_24h_has_troubleshooting(self):
        text = (ROOT / "START_24H.md").read_text(encoding="utf-8")
        self.assertIn("Troubleshooting", text)
        self.assertIn("FORGE_NUM_PREDICT", text)
        self.assertIn("SEARCH/REPLACE", text)
        self.assertIn("waiting_human", text)
        self.assertIn("Launch Checklist", text)


if __name__ == "__main__":
    unittest.main()
