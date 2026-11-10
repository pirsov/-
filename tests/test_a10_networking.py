#!/usr/bin/env python3
"""A10.2 networking glue — network_remote@v1.1 + system.coin_sync E2E."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestNetworkRemoteV11(unittest.TestCase):
    def test_registry_has_v11(self):
        from forge import skeletons_hub

        reg = skeletons_hub.load_registry(ROOT)
        meta = reg["archetypes"]["network_remote"]
        self.assertIn("v1.1", meta["versions"])
        self.assertEqual(meta["latest"], "v1")  # game1 stays on v1
        loaded = skeletons_hub.load_meta("network_remote", "v1.1", ROOT)
        assert loaded is not None
        self.assertIn("CoinSync", loaded["required"])
        self.assertIn("DataStoreService", loaded["forbid"])

    def test_bundle_v11_only(self):
        from forge import skills_hub

        blob = skills_hub.bundle_for_14b(
            ROOT, [], archetype="network_remote", skeleton_version="v1.1", skeleton_budget=700
        )
        self.assertIn("SKELETON network_remote@v1.1", blob)
        self.assertIn("CoinSync", blob)
        self.assertNotIn("SKELETON datastore_service", blob)
        self.assertLessEqual(len(blob), 2800)

    def test_game1_remotes_still_pin_v1(self):
        from forge.skeletons_hub import find_contract_pin

        pin = find_contract_pin(ROOT, ROOT / "src/shared/Gameplay/Remotes.luau")
        self.assertEqual(pin, ("network_remote", "v1"))


class TestCoinSyncGate(unittest.TestCase):
    def test_client_plan_blocks_datastore(self):
        from forge import contract_index

        ok, blocked, report = contract_index.gate_plan(
            ROOT,
            {
                "archetype": "client_ui",
                "side": "client",
                "target_path": "artifacts/a10_2_e2e/CoinHUD.client.luau",
                "proposed_calls": ["DataStoreService", "GetAsync", "CoinSync", "OnClientEvent"],
            },
        )
        self.assertFalse(ok)
        self.assertTrue(report.get("client_side"))
        self.assertTrue(any(x in blocked for x in ("DataStoreService", "GetAsync")), blocked)

    def test_client_plan_allows_remotes_only(self):
        from forge import planner

        report = planner.gate_and_plan(
            ROOT,
            {
                "plugin": "system.coin_sync.client",
                "archetype": "client_ui",
                "side": "client",
                "target_path": "artifacts/a10_2_e2e/CoinHUD.client.luau",
                "proposed_calls": [
                    "OnClientEvent",
                    "CoinSync",
                    "LocalPlayer",
                    "ScreenGui",
                    "GetAttribute",
                ],
            },
            retry=False,
        )
        self.assertEqual(report["action"], "enqueue", report)

    def test_server_plan_fireclient_ok(self):
        from forge import planner

        report = planner.gate_and_plan(
            ROOT,
            {
                "plugin": "system.coin_sync.server",
                "archetype": "server_script",
                "side": "server",
                "proposed_calls": ["FireClient", "CoinSync", "GetAttribute", "Players"],
            },
            retry=False,
        )
        self.assertEqual(report["action"], "enqueue", report)

    def test_forbid_from_contract_blocks(self):
        from forge import contract_index

        # Remotes.CoinsCollected is in forbids of coin_sync contracts
        ok, blocked, report = contract_index.gate_plan(
            ROOT,
            {"proposed_calls": ["Remotes.CoinsCollected"]},
        )
        self.assertFalse(ok)
        self.assertTrue(blocked)


class TestCoinSyncE2E(unittest.TestCase):
    def test_artifacts_validate(self):
        from forge.validator import validate_file
        from forge.skeletons_hub import find_contract_pin

        remotes = ROOT / "artifacts/a10_2_e2e/Remotes.luau"
        server = ROOT / "artifacts/a10_2_e2e/CoinSync.server.luau"
        client = ROOT / "artifacts/a10_2_e2e/CoinHUD.client.luau"
        bad = ROOT / "artifacts/a10_2_e2e/CoinHUD_BAD.client.luau"

        self.assertEqual(find_contract_pin(ROOT, remotes)[0], "network_remote")
        self.assertEqual(find_contract_pin(ROOT, remotes)[1], "v1.1")
        self.assertEqual(find_contract_pin(ROOT, server), ("server_script", "v1"))
        self.assertEqual(find_contract_pin(ROOT, client), ("client_ui", "v1"))

        ok_r, err_r = validate_file(remotes, root=ROOT)
        ok_s, err_s = validate_file(server, root=ROOT)
        ok_c, err_c = validate_file(client, root=ROOT)
        ok_b, err_b = validate_file(bad, root=ROOT)

        self.assertTrue(ok_r, err_r)
        self.assertTrue(ok_s, err_s)
        self.assertTrue(ok_c, err_c)
        self.assertFalse(ok_b)
        self.assertTrue(any("DataStore" in e for e in err_b), err_b)

    def test_v11_meta_rejects_missing_coinsync(self):
        from forge.validator import validate_file

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(ROOT / "skeletons", root / "skeletons")
            (root / "PROJECT_TZ.md").write_text("# t\n", encoding="utf-8")
            f = root / "artifacts" / "Remotes.luau"
            f.parent.mkdir(parents=True)
            f.write_text(
                "--!strict\n"
                "local function getOrCreate(name: string): RemoteEvent\n"
                "\treturn Instance.new(\"RemoteEvent\") :: RemoteEvent\n"
                "end\n"
                "local Remotes = { CoinCollected = getOrCreate(\"CoinCollected\") }\n"
                "return Remotes\n",
                encoding="utf-8",
            )
            (root / "contracts").mkdir()
            (root / "contracts" / "x.json").write_text(
                json.dumps(
                    {
                        "plugin": "x",
                        "archetype": "network_remote",
                        "skeleton_version": "v1.1",
                        "contract_snapshot": {
                            "files": ["artifacts/Remotes.luau"],
                            "archetype": "network_remote",
                            "skeleton_version": "v1.1",
                        },
                    }
                ),
                encoding="utf-8",
            )
            ok, errs = validate_file(f, root=root)
            self.assertFalse(ok)
            self.assertTrue(any("CoinSync" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
