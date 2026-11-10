#!/usr/bin/env python3
"""A23.0 — client_script archetype routing + Remotes WaitForChild + 7B DONE reminder."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class TestClientScriptRouting(unittest.TestCase):
    def test_effects_and_camera_use_client_script(self):
        from forge.skeletons_hub import (
            client_archetype_from_name,
            hard_archetype_from_path,
            infer_archetype_from_path,
            resolve_archetype_for_path,
        )

        for rel in (
            "src/client/Effects.client.luau",
            "src/client/Camera.client.luau",
            "src/client/SoundAmbience.client.luau",
            "src/client/VFX.client.luau",
        ):
            p = Path(rel)
            self.assertEqual(client_archetype_from_name(p.name), "client_script", rel)
            self.assertEqual(hard_archetype_from_path(p), "client_script", rel)
            self.assertEqual(infer_archetype_from_path(p), "client_script", rel)
            arch, _ = resolve_archetype_for_path(p, ROOT)
            self.assertEqual(arch, "client_script", rel)

    def test_hud_menu_use_client_ui(self):
        from forge.skeletons_hub import (
            hard_archetype_from_path,
            infer_archetype_from_path,
            resolve_archetype_for_path,
        )

        for rel in (
            "src/client/HUD.client.luau",
            "src/client/UI/Menu.client.luau",
            "src/client/Buttons.client.luau",
            "src/client/Leaderboard.client.luau",
        ):
            p = Path(rel)
            self.assertEqual(hard_archetype_from_path(p), "client_ui", rel)
            self.assertEqual(infer_archetype_from_path(p), "client_ui", rel)
            arch, _ = resolve_archetype_for_path(p, ROOT)
            self.assertEqual(arch, "client_ui", rel)

    def test_effects_not_forced_screengui_meta(self):
        """Effects.client.luau must validate as client_script — no ScreenGui required_any."""
        from forge.skeletons_hub import load_meta, validate_against_skeleton

        meta = load_meta("client_script", "v1", ROOT)
        self.assertIsNotNone(meta)
        req_any = meta.get("required_any") or []
        flat = {str(x) for group in req_any for x in (group if isinstance(group, list) else [])}
        self.assertNotIn("ScreenGui", flat)
        self.assertNotIn("TextLabel", flat)

        p = ROOT / "src/client/Effects.client.luau"
        # Minimal LocalScript body — no ScreenGui/TextLabel (would fail client_ui@v1)
        body = (
            "--!strict\n"
            'local Players = game:GetService("Players")\n'
            "local player = Players.LocalPlayer\n"
            'local SoundService = game:GetService("SoundService")\n'
            "local _ = SoundService\n"
        )
        errs = validate_against_skeleton(p, body, ROOT)
        self.assertEqual(errs, [], errs)
        self.assertFalse(any("ScreenGui" in e for e in errs))

    def test_planner_wires_client_script_routing(self):
        from forge.planner import resolve_client_skeleton_for_path

        arch, _ = resolve_client_skeleton_for_path(
            ROOT, "src/client/Effects.client.luau"
        )
        self.assertEqual(arch, "client_script")
        arch_ui, _ = resolve_client_skeleton_for_path(ROOT, "src/client/HUD.client.luau")
        self.assertEqual(arch_ui, "client_ui")

    def test_registry_lists_client_script(self):
        from forge.skeletons_hub import list_archetypes, load_skeleton_text

        ids = {a["id"] for a in list_archetypes(ROOT)}
        self.assertIn("client_script", ids)
        text = load_skeleton_text("client_script", "v1", ROOT)
        self.assertIn("client_script@v1", text)
        self.assertIn("LocalPlayer", text)
        # Skeleton body must not Instant.new a UI root (comment-only mentions are ok)
        self.assertNotIn('Instance.new("ScreenGui")', text)


class TestRemotesStrictRule(unittest.TestCase):
    def test_strict_rules_require_waitforchild_gameplay_remotes(self):
        from forge.prompts import build_prompt
        from forge.task_parser import Task, WriteMode

        task = Task(
            raw="- [ ] T8 | REWRITE Effects | @client_programmer | -> "
            "src/client/Effects.client.luau",
            task_id="T8",
            owner="client_programmer",
            mode=WriteMode.REWRITE,
            target_path="src/client/Effects.client.luau",
            requires_file=True,
            description="REWRITE Effects",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text(
                "# Agents\n### @client_programmer\nWrite Luau.\n",
                encoding="utf-8",
            )
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n- [ ] T8 | REWRITE Effects | @client_programmer | "
                "-> src/client/Effects.client.luau\n",
                encoding="utf-8",
            )
            (root / "state.json").write_text("{}", encoding="utf-8")
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "client_programmer",
                    task,
                    prompt_budget_tokens=4000,
                )
            needle = (
                'ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes")'
            )
            self.assertIn(needle, prompt)
            # Compact STRICT path also mentions WaitForChild Remotes
            self.assertTrue(
                "WaitForChild(\"Gameplay\")" in prompt
                or "WaitForChild('Gameplay')" in prompt
                or needle in prompt
            )
            # Must not instruct bare ReplicatedStorage.Remotes as the require path
            self.assertNotIn(
                "require(ReplicatedStorage.Remotes)",
                prompt,
            )


class TestRepairXmlDoneReminder(unittest.TestCase):
    def test_repair_mode_block_has_done_reminder(self):
        from forge.prompts import build_prompt
        from forge.task_parser import Task, WriteMode

        task = Task(
            raw="- [ ] T3 | REWRITE Checkpoints | @gameplay_programmer | -> "
            "src/server/Gameplay/Checkpoints.server.luau",
            task_id="T3",
            owner="gameplay_programmer",
            mode=WriteMode.REWRITE,
            target_path="src/server/Gameplay/Checkpoints.server.luau",
            requires_file=True,
            description="REWRITE Checkpoints",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text(
                "# Agents\n### @gameplay_programmer\nWrite Luau.\n",
                encoding="utf-8",
            )
            (root / "PROJECT_TZ.md").write_text("# TZ\n", encoding="utf-8")
            (root / "state.json").write_text("{}", encoding="utf-8")
            prompt = build_prompt(
                root,
                "gameplay_programmer",
                task,
                attempt=2,
                validator_feedback="REPAIR CHECKLIST:\n1. missing Died",
                repair_draft="local x = 1\n",
                is_7b=True,
                prompt_budget_tokens=2000,
            )
            self.assertIn(
                "START YOUR REPLY WITH <DONE>T3</DONE>. DO NOT FORGET THE XML TAGS.",
                prompt,
            )

    def test_orchestrator_repair_feedback_has_done_reminder(self):
        from forge.orchestrator import Orchestrator

        bad = (
            "<DONE>T3</DONE>\n<NOTE>bad</NOTE>\n"
            '<FILE path="src/server/Gameplay/Checkpoints.server.luau">\n'
            "--!strict\nlocal Players = game:GetService(\"Players\")\n"
            "</FILE>\n"
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text(
                "# Agents\n### @gameplay_programmer\nWrite Luau.\n",
                encoding="utf-8",
            )
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n- [ ] T3 | REWRITE Checkpoints | @gameplay_programmer | "
                "-> src/server/Gameplay/Checkpoints.server.luau\n",
                encoding="utf-8",
            )
            (root / "state.json").write_text(
                '{"task_queue":[{"id":"T3","status":"ready"}],'
                '"open_questions":[],"pulse":{"ok":true},"done":[]}',
                encoding="utf-8",
            )
            (root / "logs").mkdir(parents=True, exist_ok=True)
            (root / ".forge" / "snapshots").mkdir(parents=True, exist_ok=True)
            target = root / "src/server/Gameplay/Checkpoints.server.luau"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("--!strict\n", encoding="utf-8")

            captured: list[str] = []
            real_build = __import__("forge.prompts", fromlist=["build_prompt"]).build_prompt

            def wrap_build(*args, **kwargs):
                vf = kwargs.get("validator_feedback")
                if vf:
                    captured.append(vf)
                return real_build(*args, **kwargs)

            orch = Orchestrator(root, mock_responses={"T3": [bad, bad, bad]})
            with patch(
                "forge.orchestrator.validate_file",
                return_value=(False, ["BreakJoints is deprecated"]),
            ), patch("forge.orchestrator.build_prompt", side_effect=wrap_build):
                orch.invoke_step()

            self.assertTrue(captured, "expected repair validator_feedback")
            joined = "\n---\n".join(captured)
            self.assertIn(
                "START YOUR REPLY WITH <DONE>T3</DONE>. DO NOT FORGET THE XML TAGS.",
                joined,
            )


if __name__ == "__main__":
    unittest.main()
