#!/usr/bin/env python3
"""A14 activate: dry-run skips BAD/legacy; if_present gates require_*."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestIfPresentGate(unittest.TestCase):
    def test_require_skipped_without_gate(self):
        from forge.feedback import apply_checks_to_text

        checks = [
            {
                "type": "require_regex",
                "pattern": r"\bpcall\s*\(",
                "if_present": "re:(?:GetAsync|SetAsync)\\s*\\(",
                "msg": "need pcall",
            }
        ]
        # no DS calls → no error
        self.assertEqual(apply_checks_to_text("print(1)\n", checks, rule_id="R004"), [])
        # DS without pcall → error
        errs = apply_checks_to_text("store:SetAsync(k,1)\n", checks, rule_id="R004")
        self.assertTrue(errs)
        # DS with pcall → ok
        self.assertEqual(
            apply_checks_to_text("pcall(function() store:SetAsync(k,1) end)\n", checks, rule_id="R004"),
            [],
        )


class TestActivateCritical(unittest.TestCase):
    def test_r001_r004_r006_active_in_kb(self):
        kb = json.loads((ROOT / "knowledge_base.json").read_text(encoding="utf-8"))
        by_id = {r["id"]: r for r in kb.get("rules") or []}
        for rid in ("R001", "R004", "R006"):
            self.assertIn(rid, by_id)
            self.assertEqual(by_id[rid].get("status"), "active", rid)

    def test_dry_run_skips_legacy_bad(self):
        from forge import feedback

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "src" / "client").mkdir(parents=True)
            (root / "legacy_project" / "src" / "client").mkdir(parents=True)
            (root / "src" / "client" / "HUD.client.luau").write_text(
                "local Players = game:GetService(\"Players\")\n", encoding="utf-8"
            )
            (root / "legacy_project" / "src" / "client" / "ShopUI.client.luau").write_text(
                'local DataStoreService = game:GetService("DataStoreService")\n',
                encoding="utf-8",
            )
            (root / "src" / "client" / "Evil_BAD.client.luau").write_text(
                'local DataStoreService = game:GetService("DataStoreService")\n',
                encoding="utf-8",
            )
            rule = {
                "id": "R001",
                "match": {"archetypes": ["client_ui"]},
                "checks": [{"type": "forbid_substr", "text": "DataStoreService", "msg": "no ds"}],
            }
            ok, errs = feedback.dry_run_rule_on_golden(root, rule)
            self.assertTrue(ok, errs)


if __name__ == "__main__":
    unittest.main()
