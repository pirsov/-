#!/usr/bin/env python3
"""A10.1 datastore_service@v1 — skeleton, gate, bundle, validator."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestDatastoreSkeleton(unittest.TestCase):
    def test_registry_lists_datastore_service(self):
        from forge import skeletons_hub

        ids = {a["id"] for a in skeletons_hub.list_archetypes(ROOT)}
        self.assertIn("datastore_service", ids)
        meta = skeletons_hub.load_meta("datastore_service", "v1", ROOT)
        assert meta is not None
        self.assertIn("DataStoreService", meta["required"])
        self.assertIn("GetDataStore", meta["required"])
        self.assertIn("pcall", meta["required"])
        self.assertIn("ScreenGui", meta["forbid"])
        self.assertIn("LocalPlayer", meta["forbid"])

    def test_infer_playersave_name(self):
        from forge.skeletons_hub import infer_archetype_from_path

        self.assertEqual(
            infer_archetype_from_path(Path("src/server/Data/PlayerSave.server.luau")),
            "datastore_service",
        )
        # legacy attrs-only name stays generic server until contract pin
        self.assertEqual(
            infer_archetype_from_path(Path("src/server/Data/PlayerData.server.luau")),
            "server_script",
        )

    def test_bundle_only_datastore_skeleton(self):
        from forge import skills_hub

        blob = skills_hub.bundle_for_14b(
            ROOT, [], archetype="datastore_service", skeleton_version="v1"
        )
        self.assertIn("SKELETON datastore_service@v1", blob)
        self.assertIn("DataStoreService", blob)
        self.assertNotIn("SKELETON client_ui", blob)
        self.assertNotIn("SKELETON server_script", blob)
        self.assertLessEqual(len(blob), 2500)


class TestDatastoreE2E(unittest.TestCase):
    def test_gate_enqueue_legal_calls(self):
        from forge import planner

        plan = {
            "plugin": "system.player_save",
            "proposed_calls": [
                "DataStoreService",
                "GetDataStore",
                "GetAsync",
                "SetAsync",
                "get_player_coins",
                "PlayerRemoving",
            ],
        }
        report = planner.gate_and_plan(ROOT, plan, retry=False)
        self.assertEqual(report["action"], "enqueue", report)

    def test_gate_blocks_hallucination(self):
        from forge import planner

        plan = {
            "plugin": "system.player_save",
            "proposed_calls": ["SavePlayerForeverMagic", "GetBestTime"],
        }
        report = planner.gate_and_plan(ROOT, plan, retry=False)
        self.assertEqual(report["action"], "enqueue_blocked", report)
        self.assertTrue(report.get("unknown"))

    def test_artifact_player_save_passes(self):
        from forge.validator import validate_file

        path = ROOT / "artifacts/a10_e2e/PlayerSave.server.luau"
        ok, errs = validate_file(path, root=ROOT)
        self.assertTrue(ok, errs)

    def test_client_datastore_fails(self):
        from forge.validator import validate_file

        path = ROOT / "artifacts/a10_e2e/PlayerSave_BAD.client.luau"
        ok, errs = validate_file(path, root=ROOT)
        self.assertFalse(ok)
        self.assertTrue(
            any("DataStore" in e or "forbidden" in e.lower() for e in errs),
            errs,
        )

    def test_pinned_meta_requires_pcall(self):
        import json
        from forge.validator import validate_file

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(ROOT / "skeletons", root / "skeletons")
            (root / "PROJECT_TZ.md").write_text("# t\n", encoding="utf-8")
            f = root / "src" / "server" / "Data" / "PlayerSave.server.luau"
            f.parent.mkdir(parents=True)
            # Has DataStore markers but missing pcall → must fail META
            f.write_text(
                "--!strict\n"
                "local DataStoreService = game:GetService(\"DataStoreService\")\n"
                "local store = DataStoreService:GetDataStore(\"X\")\n"
                "local Players = game:GetService(\"Players\")\n"
                "Players.PlayerRemoving:Connect(function(p)\n"
                "\tstore:SetAsync(\"k\", 1)\n"
                "end)\n",
                encoding="utf-8",
            )
            (root / "contracts").mkdir()
            (root / "contracts" / "system.player_save.json").write_text(
                json.dumps(
                    {
                        "plugin": "system.player_save",
                        "archetype": "datastore_service",
                        "skeleton_version": "v1",
                        "contract_snapshot": {
                            "files": ["src/server/Data/PlayerSave.server.luau"],
                            "archetype": "datastore_service",
                            "skeleton_version": "v1",
                        },
                    }
                ),
                encoding="utf-8",
            )
            ok, errs = validate_file(f, root=root)
            self.assertFalse(ok)
            self.assertTrue(any("pcall" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
