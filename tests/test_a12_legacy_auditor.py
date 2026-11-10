#!/usr/bin/env python3
"""A12.0 legacy auditor — pitfalls → draft KB rules."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _write_legacy(td: Path) -> Path:
    proj = td / "legacy_project"
    server = proj / "src" / "server"
    client = proj / "src" / "client"
    server.mkdir(parents=True)
    client.mkdir(parents=True)
    (server / "SaveCoins.server.luau").write_text(
        "--!strict\n"
        "local DataStoreService = game:GetService(\"DataStoreService\")\n"
        "local store = DataStoreService:GetDataStore(\"Coins\")\n"
        "local function save(player)\n"
        "\tstore:SetAsync(\"p_\" .. player.UserId, 1)  -- no pcall — CRASH risk\n"
        "end\n"
        "local Remotes = { Buy = Instance.new(\"RemoteEvent\") }\n"
        "Remotes.Buy.OnServerEvent:Connect(function(player, pack)\n"
        "\t-- no typeof check — exploit\n"
        "\tsave(player)\n"
        "end)\n"
        "while true do\n"
        "\tprint(\"spin\")  -- no wait\n"
        "end\n",
        encoding="utf-8",
    )
    (client / "Shop.client.luau").write_text(
        "--!strict\n"
        "local Players = game:GetService(\"Players\")\n"
        "local ds = game:GetService(\"DataStoreService\")  -- forbidden on client\n"
        "local rem = Instance.new(\"RemoteEvent\")\n"
        "rem:FireServer(999)\n",
        encoding="utf-8",
    )
    return proj


class TestLegacyAuditor(unittest.TestCase):
    def test_decompose_and_pitfalls(self):
        from forge import legacy_auditor

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            proj = _write_legacy(td_path)
            forge = td_path / "forge_root"
            (forge / "docs").mkdir(parents=True)
            (forge / "state.json").write_text(
                json.dumps({"done": [], "task_queue": []}), encoding="utf-8"
            )
            (forge / "knowledge_base.json").write_text(
                json.dumps({"version": 1, "rules": [], "plugins": {}}), encoding="utf-8"
            )

            report = legacy_auditor.audit_legacy(proj, forge_root=forge, merge_kb=True)
            self.assertTrue(report["ok"])
            self.assertGreaterEqual(report["modules"], 2)
            self.assertGreaterEqual(report["functions"], 1)
            self.assertGreaterEqual(report["pitfalls"], 3)

            titles = " ".join(p["title"] for p in report["_pitfalls"])
            self.assertIn("pcall", titles.lower())
            self.assertTrue(
                any("DataStoreService on client" in p["title"] for p in report["_pitfalls"])
                or "DataStoreService" in titles
            )
            self.assertTrue(any("while true" in p["title"] for p in report["_pitfalls"]))
            self.assertTrue(
                any("OnServerEvent" in p["title"] for p in report["_pitfalls"])
            )

            arch = Path(report["architecture"])
            pit = Path(report["pitfalls_md"])
            self.assertTrue(arch.is_file())
            self.assertTrue(pit.is_file())
            self.assertIn("SaveCoins", arch.read_text(encoding="utf-8"))
            self.assertIn("P00", pit.read_text(encoding="utf-8"))

            kb = json.loads((forge / "knowledge_base.json").read_text(encoding="utf-8"))
            drafts = [r for r in kb["rules"] if r.get("status") == "draft"]
            self.assertGreaterEqual(len(drafts), 1)
            self.assertTrue(all(r.get("source") == "legacy_audit" for r in drafts))

    def test_cli_path_missing(self):
        from forge.orchestrator import main

        code = main(["--audit-legacy", "/no/such/legacy/path/xyz", "--root", str(ROOT)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
