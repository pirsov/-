#!/usr/bin/env python3
"""A10.3 HITL rules on archetypes + A10.4 system.donation_shop full-stack."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestA103RulesE2E(unittest.TestCase):
    def test_runstartedat_hitl_blocks_client_and_remotes(self):
        from forge import feedback
        from forge.validator import validate_file

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(ROOT / "skeletons", root / "skeletons")
            (root / "PROJECT_TZ.md").write_text("# t\n", encoding="utf-8")
            (root / "state.json").write_text(
                json.dumps({"done": [], "task_queue": [], "pulse": {"cycle": 1}}),
                encoding="utf-8",
            )
            (root / "knowledge_base.json").write_text(
                json.dumps({"version": 1, "rules": [], "plugins": {}}),
                encoding="utf-8",
            )
            # Clean client + remotes trees (no RunStartedAt) so dry-run activates
            client = root / "src" / "client" / "HUD.client.luau"
            client.parent.mkdir(parents=True)
            client.write_text(
                "--!strict\nlocal Players = game:GetService(\"Players\")\n"
                "local player = Players.LocalPlayer\n"
                "local gui = Instance.new(\"ScreenGui\")\n"
                "gui.Parent = player:WaitForChild(\"PlayerGui\")\n",
                encoding="utf-8",
            )
            remotes = root / "src" / "shared" / "Gameplay" / "Remotes.luau"
            remotes.parent.mkdir(parents=True)
            remotes.write_text(
                (ROOT / "skeletons/network_remote/v1.1/SKELETON.luau").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (root / "contracts").mkdir()
            (root / "contracts" / "game1.hud.json").write_text(
                json.dumps(
                    {
                        "plugin": "game1.hud",
                        "archetype": "client_ui",
                        "skeleton_version": "v1",
                        "contract_snapshot": {
                            "files": ["src/client/HUD.client.luau"],
                            "archetype": "client_ui",
                            "skeleton_version": "v1",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "contracts" / "game1.remotes.json").write_text(
                json.dumps(
                    {
                        "plugin": "game1.remotes",
                        "archetype": "network_remote",
                        "skeleton_version": "v1.1",
                        "contract_snapshot": {
                            "files": ["src/shared/Gameplay/Remotes.luau"],
                            "archetype": "network_remote",
                            "skeleton_version": "v1.1",
                        },
                    }
                ),
                encoding="utf-8",
            )

            old = os.environ.get("FORGE_RULES_AUTO")
            try:
                os.environ["FORGE_RULES_AUTO"] = "1"
                report = feedback.submit_verdict(
                    root,
                    "game1.hud",
                    "n",
                    note="Нет: RunStartedAt в UI — таймер только на сервере",
                    files=["HUD.client.luau", "Remotes.luau"],
                )
            finally:
                if old is None:
                    os.environ.pop("FORGE_RULES_AUTO", None)
                else:
                    os.environ["FORGE_RULES_AUTO"] = old

            rule = report["rule"]
            self.assertEqual(rule.get("status"), "active", report)
            checks = rule.get("checks") or []
            self.assertTrue(any("RunStartedAt" in str(c.get("pattern")) for c in checks), checks)
            arch = (rule.get("match") or {}).get("archetypes") or []
            self.assertIn("client_ui", arch)

            # Inject RunStartedAt into client_ui → FAIL
            client.write_text(
                client.read_text(encoding="utf-8") + '\nlocal t = player:GetAttribute("RunStartedAt")\n',
                encoding="utf-8",
            )
            ok_c, err_c = validate_file(client, root=root)
            self.assertFalse(ok_c)
            self.assertTrue(any("RunStartedAt" in e or "HITL" in e or "R" in e for e in err_c), err_c)

            # Inject into Remotes (network_remote) → FAIL via archetype match
            remotes.write_text(
                remotes.read_text(encoding="utf-8") + "\n-- leak RunStartedAt\n",
                encoding="utf-8",
            )
            # comments stripped in skeleton META but HITL apply_checks uses raw content
            ok_r, err_r = validate_file(remotes, root=root)
            self.assertFalse(ok_r)
            self.assertTrue(any("RunStartedAt" in e or "HITL" in e or "R" in e for e in err_r), err_r)


class TestA104DonationShop(unittest.TestCase):
    def test_pins_and_validate_parts(self):
        from forge.skeletons_hub import find_contract_pin
        from forge.validator import validate_file

        remotes = ROOT / "artifacts/a10_4_e2e/Remotes.luau"
        server = ROOT / "artifacts/a10_4_e2e/DonationShop.server.luau"
        client = ROOT / "artifacts/a10_4_e2e/DonationShop.client.luau"

        self.assertEqual(find_contract_pin(ROOT, remotes), ("network_remote", "v1.1"))
        self.assertEqual(find_contract_pin(ROOT, server), ("datastore_service", "v1"))
        self.assertEqual(find_contract_pin(ROOT, client), ("client_ui", "v1.1"))

        ok_r, err_r = validate_file(remotes, root=ROOT)
        ok_s, err_s = validate_file(server, root=ROOT)
        ok_c, err_c = validate_file(client, root=ROOT)
        self.assertTrue(ok_r, err_r)
        self.assertTrue(ok_s, err_s)
        self.assertTrue(ok_c, err_c)

    def test_planner_split_gates(self):
        from forge import planner

        tz = json.loads((ROOT / "artifacts/a10_4_e2e/tz_task.json").read_text(encoding="utf-8"))
        for part in tz["planner_split"]:
            report = planner.gate_and_plan(
                ROOT,
                {
                    "plugin": f"system.donation_shop.{ 'remotes' if part['archetype']=='network_remote' else ('server' if part['archetype']=='datastore_service' else 'client') }",
                    "archetype": part["archetype"],
                    "side": part.get("side"),
                    "target_path": part["target_path"],
                    "proposed_calls": part["proposed_calls"],
                },
                retry=False,
            )
            self.assertEqual(report["action"], "enqueue", (part["id"], report))

        # Cross-skeleton leaks blocked
        bad_client = planner.gate_and_plan(
            ROOT,
            {
                "plugin": "system.donation_shop.client",
                "archetype": "client_ui",
                "side": "client",
                "proposed_calls": ["DataStoreService", "GetAsync", "DonateRequest"],
            },
            retry=False,
        )
        self.assertEqual(bad_client["action"], "enqueue_blocked", bad_client)

        bad_remotes = planner.gate_and_plan(
            ROOT,
            {
                "plugin": "system.donation_shop.remotes",
                "archetype": "network_remote",
                "proposed_calls": ["GetAsync", "DonateRequest"],
            },
            retry=False,
        )
        self.assertEqual(bad_remotes["action"], "enqueue_blocked", bad_remotes)

    def test_client_v11_allows_fireserver_meta(self):
        from forge import skeletons_hub

        meta = skeletons_hub.load_meta("client_ui", "v1.1", ROOT)
        assert meta is not None
        self.assertNotIn("FireServer", meta.get("forbid") or [])
        self.assertIn("DataStoreService", meta.get("forbid") or [])
        self.assertIn("RunStartedAt", " ".join(meta.get("forbid_regex") or []))

    def test_bundles_per_archetype(self):
        from forge import skills_hub

        b_r = skills_hub.bundle_for_14b(
            ROOT, [], archetype="network_remote", skeleton_version="v1.1", skeleton_budget=700
        )
        b_s = skills_hub.bundle_for_14b(
            ROOT, [], archetype="datastore_service", skeleton_version="v1"
        )
        b_c = skills_hub.bundle_for_14b(
            ROOT, [], archetype="client_ui", skeleton_version="v1.1"
        )
        self.assertIn("CoinSync", b_r)
        self.assertIn("DataStoreService", b_s)
        self.assertIn("FireServer", b_c)
        self.assertNotIn("SKELETON datastore_service", b_c)


if __name__ == "__main__":
    unittest.main()
