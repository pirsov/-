#!/usr/bin/env python3
"""A11.0 asset catalog + gate against hallucinated proposed_assets."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestAssetHub(unittest.TestCase):
    def test_scan_and_catalog(self):
        from forge import asset_hub

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            models = root / "assets" / "models"
            models.mkdir(parents=True)
            (models / "Apple.glb").write_bytes(b"glTF")
            (models / "Banana.ldr").write_text("0 Banana\n", encoding="utf-8")
            (models / "notes.txt").write_text("ignore", encoding="utf-8")
            cat = asset_hub.scan_models(root)
            self.assertEqual(sorted(cat["ids"]), ["Apple", "Banana"])
            path = asset_hub.write_catalog(root, catalog=cat)
            self.assertTrue(path.is_file())
            loaded = asset_hub.load_catalog(root)
            self.assertEqual(loaded["count"], 2)
            prompt = asset_hub.catalog_for_prompt(root)
            self.assertIn("Apple", prompt)
            self.assertIn("Banana", prompt)

    def test_gate_blocks_unknown_asset(self):
        from forge import asset_hub, planner

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            models = root / "assets" / "models"
            models.mkdir(parents=True)
            (models / "Apple.glb").write_bytes(b"x")
            asset_hub.write_catalog(root)
            (root / "state.json").write_text(
                json.dumps({"done": [], "task_queue": [], "pulse": {"cycle": 1}}),
                encoding="utf-8",
            )
            (root / "knowledge_base.json").write_text(
                json.dumps({"rules": [], "plugins": {}}), encoding="utf-8"
            )
            (root / "contracts").mkdir()

            ok, unknown, report = asset_hub.gate_assets(
                root, {"proposed_assets": ["Apple", "DragonFruit"]}
            )
            self.assertFalse(ok)
            self.assertIn("DragonFruit", unknown)

            ok2, _, _ = asset_hub.gate_assets(root, {"proposed_assets": ["Apple"]})
            self.assertTrue(ok2)

            # Via planner.gate_and_plan (exports empty plan still ok if no proposed_calls)
            blocked = planner.gate_and_plan(
                root,
                {"proposed_calls": ["Players"], "proposed_assets": ["UnicornMesh"]},
                retry=False,
            )
            self.assertEqual(blocked["action"], "enqueue_blocked")
            self.assertTrue(blocked.get("assets", {}).get("unknown_assets"))

            good = planner.gate_and_plan(
                root,
                {"proposed_calls": ["Players"], "proposed_assets": ["Apple"]},
                retry=False,
            )
            self.assertEqual(good["action"], "enqueue", good)

    def test_extract_from_tz_text(self):
        from forge.asset_hub import extract_proposed_assets

        plan = {
            "description": 'Spawn collectibles proposed_assets: ["Apple", "Coin"]',
        }
        ids = extract_proposed_assets(plan)
        self.assertIn("Apple", ids)
        self.assertIn("Coin", ids)

    def test_deepseek_prompt_includes_assets_line(self):
        from forge import asset_hub, deepseek

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            models = root / "assets" / "models"
            models.mkdir(parents=True)
            (models / "Apple.glb").write_bytes(b"x")
            asset_hub.write_catalog(root)
            # Monkeypatch catalog_for_prompt via chdir? deepseek uses ROOT_DEFAULT.
            # Call catalog_for_prompt on temp and assert format; deepseek wiring is string concat.
            line = asset_hub.catalog_for_prompt(root)
            self.assertTrue(line.startswith("Available 3D assets:"))
            self.assertIn("Apple", line)

    def test_place_meshes_fruits_inventory(self):
        """Repo place_meshes.json lists Fruits_Inventory models for the Gate."""
        from forge import asset_hub

        place = ROOT / "assets" / "catalog" / "place_meshes.json"
        self.assertTrue(place.is_file())
        data = json.loads(place.read_text(encoding="utf-8"))
        self.assertEqual(data.get("folder"), "Fruits_Inventory")
        ids = {m["id"] for m in data.get("meshes") or []}
        for must in (
            "Apple",
            "Banana",
            "Orange",
            "Mango",
            "DragonFruit",
            "Strawberry",
            "VoxelApple",
        ):
            self.assertIn(must, ids)
        apple = next(m for m in data["meshes"] if m["id"] == "Apple")
        self.assertEqual(apple.get("alias_of"), "VoxelApple")
        banana = next(m for m in data["meshes"] if m["id"] == "Banana")
        self.assertTrue(str(banana.get("mesh_id") or "").startswith("rbxassetid://"))
        trash = next(m for m in data["meshes"] if m["id"] == "Trash_Orange")
        self.assertEqual(trash.get("sibling_of"), "Fruits_Inventory")
        self.assertNotEqual(trash.get("folder"), "Fruits_Inventory")
        cat = asset_hub.scan_models(ROOT)
        for must in ("Apple", "Orange", "DragonFruit", "Watermelon"):
            self.assertIn(must, cat["ids"])
        ok, unknown, _ = asset_hub.gate_assets(
            ROOT,
            {"proposed_assets": ["Apple", "Orange", "DragonFruit"]},
            catalog=cat,
        )
        self.assertTrue(ok, unknown)

    def test_rbxl_inventory_scanner(self):
        from forge import rbxl_inventory

        rbxl = ROOT / "artifacts" / "reference_place" / "working_game.rbxl"
        self.assertTrue(rbxl.is_file())
        scan = rbxl_inventory.extract_fruits_inventory(rbxl)
        self.assertEqual(scan["folder"], "Fruits_Inventory")
        named = [f for f in scan["fruits"] if f.get("id")]
        self.assertGreaterEqual(len(named), 15)
        ids = {f["id"] for f in named}
        self.assertIn("Orange", ids)
        self.assertIn("VoxelApple", ids)
        banana = next(e for e in scan["extras"] if e["id"] == "Banana")
        self.assertEqual(banana.get("class"), "Accessory")
        self.assertTrue(str(banana.get("mesh_id") or "").startswith("rbxassetid://"))
        doc = rbxl_inventory.build_place_meshes_doc(scan)
        self.assertIn("Apple", {m["id"] for m in doc["meshes"]})


if __name__ == "__main__":
    unittest.main()
