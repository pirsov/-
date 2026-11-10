#!/usr/bin/env python3
"""A22.0 - Prompt STRICT RULES hardening + 7B first-error-only repair."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge.prompts import (
    FIRST_ERROR_ONLY_INSTRUCTION,
    build_prompt,
    format_validator_checklist,
    repair_errors_for_7b,
)
from forge.task_parser import Task, WriteMode


def _checkpoints_task() -> Task:
    return Task(
        raw="- [ ] T3 | REWRITE Checkpoints | @gameplay_programmer | -> "
        "src/server/Gameplay/Checkpoints.server.luau",
        task_id="T3",
        owner="gameplay_programmer",
        mode=WriteMode.REWRITE,
        target_path="src/server/Gameplay/Checkpoints.server.luau",
        requires_file=True,
        description="REWRITE Checkpoints",
    )


def _seed_root(root: Path) -> None:
    (root / "AGENTS.md").write_text(
        "# Agents\n### @gameplay_programmer\nWrite Luau.\n",
        encoding="utf-8",
    )
    (root / "PROJECT_TZ.md").write_text(
        "# TZ\n"
        "- [ ] T3 | REWRITE Checkpoints | @gameplay_programmer | -> "
        "src/server/Gameplay/Checkpoints.server.luau\n",
        encoding="utf-8",
    )
    (root / "state.json").write_text("{}", encoding="utf-8")


class TestA22StrictRulesInPrompt(unittest.TestCase):
    def test_strict_rules_include_a22_hard_caps(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    _checkpoints_task(),
                    prompt_budget_tokens=4000,
                )
            self.assertIn("HARD CAPS", prompt)
            self.assertIn("NEVER use BreakJoints", prompt)
            self.assertIn("Humanoid.Health = 0", prompt)
            self.assertIn('SetAttribute("Checkpoint", idx)', prompt)
            self.assertIn("tonumber(match)", prompt)
            self.assertIn("NEVER a Part/Instance", prompt)
            self.assertIn("MUST NOT use DataStoreService", prompt)
            self.assertIn("datastore_service archetype", prompt)
            # Still in STRICT RULES / STRICT block for 14B
            self.assertTrue(
                "STRICT RULES:" in prompt or "STRICT (ctx<=2k):" in prompt,
                "expected STRICT RULES block in 14B prompt",
            )


class TestA22FirstErrorOnlyRepair(unittest.TestCase):
    def test_repair_errors_for_7b_keeps_single(self):
        self.assertEqual(repair_errors_for_7b(["only-one"]), ["only-one"])
        self.assertEqual(repair_errors_for_7b([]), [])

    def test_repair_errors_for_7b_takes_first_of_many(self):
        errs = [
            "BreakJoints is deprecated",
            'SetAttribute("Checkpoint", part) is wrong — pass numeric idx, not a Part',
            "DataStoreService forbidden on client — use server datastore_service archetype",
        ]
        self.assertEqual(repair_errors_for_7b(errs), [errs[0]])
        self.assertEqual(len(repair_errors_for_7b(errs)), 1)

    def test_format_checklist_first_only_instruction(self):
        errs = [
            "BreakJoints is deprecated",
            'Checkpoints must SetAttribute("Checkpoint", <number>)',
            "Checkpoints.server.luau missing Humanoid.Died / LoadCharacter handling",
        ]
        text = format_validator_checklist(errs, first_only=True)
        self.assertIn("REPAIR CHECKLIST", text)
        self.assertIn("1. BreakJoints is deprecated", text)
        self.assertNotIn("2. Checkpoints must SetAttribute", text)
        self.assertNotIn("3. Checkpoints.server.luau missing", text)
        self.assertIn(FIRST_ERROR_ONLY_INSTRUCTION, text)
        self.assertIn("Deferred 2 other validator error(s)", text)

    def test_format_checklist_all_when_not_first_only(self):
        errs = ["err-a", "err-b"]
        text = format_validator_checklist(errs, first_only=False)
        self.assertIn("1. err-a", text)
        self.assertIn("2. err-b", text)
        self.assertNotIn(FIRST_ERROR_ONLY_INSTRUCTION, text)

    def test_repair_prompt_embeds_only_first_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            errs = [
                "BreakJoints is deprecated",
                'SetAttribute("Checkpoint", hit) is wrong — pass numeric idx, not a Part',
                "Checkpoints must not use DataStoreService",
            ]
            checklist = format_validator_checklist(errs, first_only=True)
            feedback = (
                "REPAIR your previous draft (do not start over).\n"
                + checklist
                + f"\n{FIRST_ERROR_ONLY_INSTRUCTION}"
            )
            prompt = build_prompt(
                root,
                "gameplay_programmer",
                _checkpoints_task(),
                attempt=2,
                validator_feedback=feedback,
                repair_draft='local x = part:BreakJoints()\n',
                is_7b=True,
                prompt_budget_tokens=2000,
            )
            self.assertIn("BreakJoints is deprecated", prompt)
            self.assertIn(FIRST_ERROR_ONLY_INSTRUCTION, prompt)
            # Second/third errors must not be fed as checklist bullets
            self.assertNotIn("2. SetAttribute", prompt)
            self.assertNotIn("3. Checkpoints must not use DataStoreService", prompt)

    def test_orchestrator_feeds_first_error_only(self):
        """Multi-fail path: repair prompt on attempt 2 embeds only the first error."""
        from forge.orchestrator import Orchestrator

        multi_errs = [
            "BreakJoints is deprecated",
            'SetAttribute("Checkpoint", part) is wrong — pass numeric idx, not a Part',
            "Checkpoints.server.luau MUST NOT use DataStoreService",
        ]
        bad = (
            "<DONE>T3</DONE>\n<NOTE>bad</NOTE>\n"
            '<FILE path="src/server/Gameplay/Checkpoints.server.luau">\n'
            "--!strict\nlocal Players = game:GetService(\"Players\")\n"
            "</FILE>\n"
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            (root / "logs").mkdir(parents=True, exist_ok=True)
            (root / ".forge" / "snapshots").mkdir(parents=True, exist_ok=True)
            target = root / "src" / "server" / "Gameplay" / "Checkpoints.server.luau"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("--!strict\n", encoding="utf-8")

            captured: list[str] = []
            real_build = __import__("forge.prompts", fromlist=["build_prompt"]).build_prompt

            def wrap_build(*args, **kwargs):
                vf = kwargs.get("validator_feedback")
                if vf:
                    captured.append(vf)
                return real_build(*args, **kwargs)

            orch = Orchestrator(
                root,
                mock_responses={"T3": [bad, bad, bad]},
            )
            with patch(
                "forge.orchestrator.validate_file",
                return_value=(False, list(multi_errs)),
            ), patch("forge.orchestrator.build_prompt", side_effect=wrap_build):
                result = orch.invoke_step()

            self.assertFalse(result.ok)
            self.assertTrue(captured, "expected validator_feedback on repair attempts")
            joined = "\n---\n".join(captured)
            self.assertIn("1. BreakJoints is deprecated", joined)
            self.assertIn(FIRST_ERROR_ONLY_INSTRUCTION, joined)
            self.assertNotIn("2. SetAttribute", joined)
            self.assertNotIn(
                "3. Checkpoints.server.luau MUST NOT use DataStoreService",
                joined,
            )
            # Prompt log is overwritten per attempt; last write is a repair prompt
            prompts = list((root / "logs").glob("*-T3-prompt.txt"))
            self.assertTrue(prompts)
            last = prompts[0].read_text(encoding="utf-8")
            self.assertIn("BreakJoints is deprecated", last)
            self.assertIn(FIRST_ERROR_ONLY_INSTRUCTION, last)


if __name__ == "__main__":
    unittest.main()
