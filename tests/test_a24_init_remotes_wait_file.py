#!/usr/bin/env python3
"""A24.0 — init_remotes skeleton + wait() critical + FILE mandatory in repair."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class TestInitRemotesRouting(unittest.TestCase):
    def test_init_remotes_hard_map(self):
        from forge.skeletons_hub import (
            hard_archetype_from_path,
            infer_archetype_from_path,
            resolve_archetype_for_path,
        )

        for rel in (
            "src/server/InitRemotes.server.luau",
            "src/server/Gameplay/InitRemotes.server.luau",
            "src/server/Init_Remotes.server.luau",
        ):
            p = Path(rel)
            self.assertEqual(hard_archetype_from_path(p), "init_remotes", rel)
            self.assertEqual(infer_archetype_from_path(p), "init_remotes", rel)
            arch, _ = resolve_archetype_for_path(p, ROOT)
            self.assertEqual(arch, "init_remotes", rel)

    def test_init_remotes_not_server_script_player_mandate(self):
        """InitRemotes must NOT fail server_script required_any Player/Workspace."""
        from forge.skeletons_hub import load_meta, validate_against_skeleton

        meta = load_meta("init_remotes", "v1", ROOT)
        self.assertIsNotNone(meta)
        req_any = meta.get("required_any") or []
        flat = {str(x) for group in req_any for x in (group if isinstance(group, list) else [])}
        self.assertNotIn("Player", flat)
        self.assertNotIn("Players", flat)
        self.assertNotIn("Workspace", flat)
        self.assertNotIn("RunService", flat)

        p = ROOT / "src/server/InitRemotes.server.luau"
        body = (
            "--!strict\n"
            'local ReplicatedStorage = game:GetService("ReplicatedStorage")\n'
            'local Remotes = require(ReplicatedStorage:WaitForChild("Gameplay")'
            ':WaitForChild("Remotes"))\n'
            'print("[InitRemotes] ready")\n'
            'local _ = Instance.new("RemoteEvent")\n'
        )
        errs = validate_against_skeleton(p, body, ROOT)
        self.assertEqual(errs, [], errs)
        self.assertFalse(any("Player" in e or "Workspace" in e for e in errs))

    def test_real_init_remotes_file_validates(self):
        from forge.skeletons_hub import validate_against_skeleton

        p = ROOT / "src/server/InitRemotes.server.luau"
        self.assertTrue(p.is_file(), p)
        body = p.read_text(encoding="utf-8")
        errs = validate_against_skeleton(p, body, ROOT)
        self.assertEqual(errs, [], errs)

    def test_planner_wires_init_remotes(self):
        from forge.planner import resolve_server_skeleton_for_path

        arch, _ = resolve_server_skeleton_for_path(
            ROOT, "src/server/InitRemotes.server.luau"
        )
        self.assertEqual(arch, "init_remotes")
        arch_void, _ = resolve_server_skeleton_for_path(
            ROOT, "src/server/Gameplay/Void.server.luau"
        )
        self.assertEqual(arch_void, "server_script")

    def test_registry_lists_init_remotes(self):
        from forge.skeletons_hub import list_archetypes, load_skeleton_text

        ids = {a["id"] for a in list_archetypes(ROOT)}
        self.assertIn("init_remotes", ids)
        text = load_skeleton_text("init_remotes", "v1", ROOT)
        self.assertIn("init_remotes@v1", text)
        self.assertIn("ReplicatedStorage", text)

    def test_wrong_server_script_on_init_remotes_is_routing_fail(self):
        from forge.skeletons_hub import is_skeleton_routing_failure

        p = Path("src/server/InitRemotes.server.luau")
        errs = [
            "[skeleton server_script@v1] missing any of "
            "['Player', 'Players', 'Workspace', 'RunService']"
        ]
        self.assertTrue(is_skeleton_routing_failure(p, errs))


class TestWaitAndRemotesStrictRules(unittest.TestCase):
    def test_strict_rules_wait_critical_and_remotes(self):
        from forge.prompts import build_prompt
        from forge.task_parser import Task, WriteMode

        task = Task(
            raw="- [ ] T11 | REWRITE InitRemotes | @gameplay_programmer | -> "
            "src/server/InitRemotes.server.luau",
            task_id="T11",
            owner="gameplay_programmer",
            mode=WriteMode.REWRITE,
            target_path="src/server/InitRemotes.server.luau",
            requires_file=True,
            description="REWRITE InitRemotes",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text(
                "# Agents\n### @gameplay_programmer\nWrite Luau.\n",
                encoding="utf-8",
            )
            (root / "PROJECT_TZ.md").write_text("# TZ\n", encoding="utf-8")
            (root / "state.json").write_text("{}", encoding="utf-8")
            with patch("forge.llm.backend_name", return_value="deepseek"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    task,
                    prompt_budget_tokens=4000,
                )
            self.assertIn(
                "NEVER use wait(). Use task.wait(). This is a critical error.",
                prompt,
            )
            needle = (
                'ALWAYS require Remotes via '
                'ReplicatedStorage:WaitForChild("Gameplay"):WaitForChild("Remotes")'
            )
            self.assertIn(needle, prompt)


class TestRepairFileMandatory(unittest.TestCase):
    def test_repair_mode_block_has_file_mandatory(self):
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
            self.assertIn(
                'You MUST include <FILE path="...">content</FILE>. The FILE tag is mandatory.',
                prompt,
            )

    def test_orchestrator_repair_feedback_has_file_mandatory(self):
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
            self.assertIn(
                'You MUST include <FILE path="...">content</FILE>. The FILE tag is mandatory.',
                joined,
            )


if __name__ == "__main__":
    unittest.main()
