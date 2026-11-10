#!/usr/bin/env python3
"""A18.1 — .server.luau → server_script hard-map + skeleton-fail short-circuit."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class TestServerLuauHardMap(unittest.TestCase):
    def test_infer_void_server_not_shared_data(self):
        from forge.skeletons_hub import hard_archetype_from_path, infer_archetype_from_path

        p = Path("src/server/Gameplay/Void.server.luau")
        self.assertEqual(hard_archetype_from_path(p), "server_script")
        self.assertEqual(infer_archetype_from_path(p), "server_script")
        self.assertNotEqual(infer_archetype_from_path(p), "shared_data")

    def test_infer_client_luau(self):
        from forge.skeletons_hub import hard_archetype_from_path, infer_archetype_from_path

        p = Path("src/client/UI/HUD.client.luau")
        self.assertEqual(hard_archetype_from_path(p), "client_ui")
        self.assertEqual(infer_archetype_from_path(p), "client_ui")

    def test_infer_effects_client_script(self):
        from forge.skeletons_hub import hard_archetype_from_path, infer_archetype_from_path

        p = Path("src/client/Effects.client.luau")
        self.assertEqual(hard_archetype_from_path(p), "client_script")
        self.assertEqual(infer_archetype_from_path(p), "client_script")

    def test_void_pin_and_validate_server_script(self):
        from forge.skeletons_hub import (
            find_contract_pin,
            resolve_archetype_for_path,
            validate_against_skeleton,
        )

        p = ROOT / "src/server/Gameplay/Void.server.luau"
        pin = find_contract_pin(ROOT, p)
        self.assertEqual(pin[0], "server_script", pin)
        arch, ver = resolve_archetype_for_path(p, ROOT)
        self.assertEqual(arch, "server_script")
        body = (
            "--!strict\n"
            'local RunService = game:GetService("RunService")\n'
            'local Players = game:GetService("Players")\n'
            "RunService.Heartbeat:Connect(function() end)\n"
        )
        errs = validate_against_skeleton(p, body, ROOT)
        self.assertEqual(errs, [], errs)
        # Must NOT demand ModuleScript return
        self.assertFalse(any("return" in e.lower() and "missing" in e.lower() for e in errs))

    def test_score_zero_never_pins_unrelated_contract(self):
        """Unrelated archetype contracts must not win with score=0."""
        from forge.skeletons_hub import find_contract_pin, resolve_archetype_for_path

        # Hypothetical path with no contract — must not inherit forge.skeletons shared_data
        p = ROOT / "src/server/Gameplay/NoSuchPlugin.server.luau"
        pin = find_contract_pin(ROOT, p)
        self.assertIsNone(pin[0], pin)
        arch, _ = resolve_archetype_for_path(p, ROOT)
        self.assertEqual(arch, "server_script")

    def test_shared_data_pin_ignored_for_server_luau(self):
        from forge.skeletons_hub import resolve_archetype_for_path

        # Even if a bad pin existed, HARD-map wins over shared_data
        p = ROOT / "src/server/Gameplay/Void.server.luau"
        with patch(
            "forge.skeletons_hub.find_contract_pin",
            return_value=("shared_data", "v1"),
        ):
            arch, _ = resolve_archetype_for_path(p, ROOT)
        self.assertEqual(arch, "server_script")

    def test_datastore_pin_still_wins_for_donation_shop(self):
        from forge.skeletons_hub import resolve_archetype_for_path

        p = ROOT / "artifacts/a10_4_e2e/DonationShop.server.luau"
        arch, ver = resolve_archetype_for_path(p, ROOT)
        self.assertEqual(arch, "datastore_service")
        self.assertEqual(ver, "v1")


class TestSkeletonRoutingShortCircuit(unittest.TestCase):
    def test_is_skeleton_routing_failure_shared_data_return(self):
        from forge.skeletons_hub import is_skeleton_routing_failure

        p = Path("src/server/Gameplay/Void.server.luau")
        errs = ["[skeleton shared_data@v1] missing required `return`"]
        self.assertTrue(is_skeleton_routing_failure(p, errs))

    def test_is_skeleton_routing_failure_ignores_real_bugs(self):
        from forge.skeletons_hub import is_skeleton_routing_failure

        p = Path("src/server/Gameplay/Checkpoints.server.luau")
        errs = [
            "Checkpoints.server.luau missing Humanoid.Died / LoadCharacter handling",
        ]
        self.assertFalse(is_skeleton_routing_failure(p, errs))

    def test_orchestrator_skips_7b_on_skeleton_routing(self):
        from forge.orchestrator import Orchestrator
        from forge import state_hub
        import json

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "logs").mkdir(parents=True, exist_ok=True)
            (root / ".forge" / "snapshots").mkdir(parents=True, exist_ok=True)
            # Minimal week root
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n\n"
                "- [ ] T1 | REWRITE Void | @gameplay_programmer | "
                "-> src/server/Gameplay/Void.server.luau\n"
                "- [ ] T2 | REWRITE Coins | @gameplay_programmer | "
                "-> src/server/Gameplay/Coins.server.luau\n",
                encoding="utf-8",
            )
            (root / "AGENTS.md").write_text(
                "# Agents\n### @gameplay_programmer\nWrite Luau.\n",
                encoding="utf-8",
            )
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "task_queue": [
                            {"id": "T1", "status": "ready"},
                            {"id": "T2", "status": "ready"},
                        ],
                        "open_questions": [],
                        "pulse": {"ok": True},
                        "done": [],
                    }
                ),
                encoding="utf-8",
            )
            target = root / "src/server/Gameplay/Void.server.luau"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("-- seed\n", encoding="utf-8")
            # Copy skeletons so validator can run if needed
            shutil.copytree(ROOT / "skeletons", root / "skeletons")
            shutil.copytree(ROOT / "contracts", root / "contracts")

            bad = (
                "<DONE>T1</DONE>\n<NOTE>bad</NOTE>\n"
                '<FILE path="src/server/Gameplay/Void.server.luau">\n'
                "--!strict\nlocal x = 1\n</FILE>\n"
            )
            orch = Orchestrator(root, mock_responses={"T1": [bad, bad, bad]})
            skel_errs = ["[skeleton shared_data@v1] missing required `return`"]
            with patch(
                "forge.orchestrator.validate_file",
                return_value=(False, skel_errs),
            ):
                result = orch.invoke_step()
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "failed_repair")
            self.assertIn("skeleton", (result.note or "").lower())
            # Must not have burned 3 repair attempts — only 1 model call
            self.assertEqual(orch._mock_idx.get("T1", 0), 1)
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("- [-] T1", tz)


class TestApiGuardInBundle(unittest.TestCase):
    def test_bundle_for_14b_brickcolor_guard(self):
        from forge import skills_hub

        blob = skills_hub.bundle_for_14b(ROOT, [], max_skills=0, skeleton_budget=0)
        self.assertIn("Do not use BrickColor for materials", blob)
        self.assertIn("Enum.Material.Neon", blob)
        self.assertIn("'Gold'", blob)
        self.assertIn("'Bright red'", blob)


if __name__ == "__main__":
    unittest.main()
