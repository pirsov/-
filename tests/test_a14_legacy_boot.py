#!/usr/bin/env python3
"""A14.0 — audit in-repo legacy_project/ + draft rules bootstrapped to KB."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "legacy_project"


class TestA14LegacyBoot(unittest.TestCase):
    def test_legacy_project_has_luau(self):
        files = list(LEGACY.rglob("*.luau"))
        self.assertGreaterEqual(len(files), 4, "legacy_project should ship Claude-Code sample Luau")

    def test_audit_writes_docs_and_drafts(self):
        from forge import legacy_auditor

        with tempfile.TemporaryDirectory() as td:
            forge = Path(td)
            (forge / "docs").mkdir()
            (forge / "knowledge_base.json").write_text(
                json.dumps({"version": 1, "rules": [], "plugins": {}}), encoding="utf-8"
            )
            report = legacy_auditor.audit_legacy(LEGACY, forge_root=forge, merge_kb=True)
            self.assertTrue(report["ok"])
            self.assertGreaterEqual(report["pitfalls"], 5)
            self.assertGreaterEqual(report["by_severity"]["crit"], 2)
            pit = Path(report["pitfalls_md"]).read_text(encoding="utf-8")
            self.assertIn("DataStore", pit)
            self.assertIn("while true", pit)
            self.assertIn("OnServerEvent", pit)
            kb = json.loads((forge / "knowledge_base.json").read_text(encoding="utf-8"))
            drafts = [r for r in kb["rules"] if r.get("status") == "draft"]
            self.assertGreaterEqual(len(drafts), 4)
            # bootstrapped rules use archetypes (apply to new gens)
            self.assertTrue(any((r.get("match") or {}).get("archetypes") for r in drafts))
            ids = [r["id"] for r in drafts]
            self.assertTrue(all(i.startswith("R") for i in ids))

    def test_docs_pitfalls_present_in_repo(self):
        pit = (ROOT / "docs" / "LEGACY_PITFALLS.md").read_text(encoding="utf-8")
        self.assertIn("legacy_project", pit)
        self.assertIn("P001", pit)
        self.assertIn("CRIT", pit)


if __name__ == "__main__":
    unittest.main()
