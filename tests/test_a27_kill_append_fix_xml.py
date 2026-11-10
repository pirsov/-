#!/usr/bin/env python3
"""A27 — Kill APPEND & Fix XML (user labeled A24.0; A24/A26 already shipped)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent

MANDATORY_FILE = (
    'MANDATORY: Your reply MUST contain <FILE path="...">content</FILE>. '
    "If you don't include the FILE tag, your fix will be rejected."
)
REMOTES_WAIT = (
    'ALWAYS require Remotes via ReplicatedStorage:WaitForChild("Gameplay")'
    ':WaitForChild("Remotes")'
)


class TestAppendCoercedToRewrite(unittest.TestCase):
    def test_detect_mode_append_is_rewrite(self):
        from forge.task_parser import WriteMode, detect_mode

        self.assertEqual(detect_mode("APPEND HUD labels"), WriteMode.REWRITE)
        self.assertEqual(detect_mode("append services/imports only"), WriteMode.REWRITE)

    def test_parse_append_task_is_rewrite(self):
        from forge.task_parser import WriteMode, parse_task_line

        line = (
            "- [ ] T20 | APPEND HUD updateCoins paste | @client_programmer | "
            "-> src/client/HUD.client.luau"
        )
        t = parse_task_line(line)
        assert t is not None
        self.assertEqual(t.mode, WriteMode.REWRITE)
        self.assertTrue(t.requires_file)

    def test_section_anchor_no_longer_forces_append(self):
        from forge.task_parser import WriteMode, parse_task_line

        line = "- [ ] T11 | GDD polish notes | @game_designer | -> docs/GDD.md#polish"
        t = parse_task_line(line)
        assert t is not None
        self.assertEqual(t.section, "polish")
        self.assertNotEqual(t.mode, WriteMode.APPEND)

    def test_mode_instructions_never_say_append(self):
        from forge.prompts import mode_instructions
        from forge.task_parser import Task, WriteMode

        for mode in (WriteMode.APPEND, WriteMode.REWRITE):
            task = Task(
                raw="- [ ] T1 | APPEND X | @client_programmer | -> src/client/HUD.client.luau",
                task_id="T1",
                owner="client_programmer",
                mode=mode,
                target_path="src/client/HUD.client.luau",
                requires_file=True,
                description="APPEND X",
            )
            text = mode_instructions(task, file_exists=True, prefer_diff=True)
            self.assertNotIn("WRITE MODE = APPEND", text)
            self.assertNotIn("Return ONLY the new lines to append", text)
            self.assertIn("REWRITE", text)

    def test_prompt_baseline_not_append_after(self):
        from forge.prompts import build_prompt
        from forge.task_parser import Task, WriteMode

        task = Task(
            raw="- [ ] T20 | APPEND HUD | @client_programmer | -> src/client/HUD.client.luau",
            task_id="T20",
            owner="client_programmer",
            mode=WriteMode.APPEND,
            target_path="src/client/HUD.client.luau",
            requires_file=True,
            description="APPEND HUD",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text("# A\n", encoding="utf-8")
            (root / "PROJECT_TZ.md").write_text("# TZ\n" + task.raw + "\n", encoding="utf-8")
            hud = root / "src" / "client" / "HUD.client.luau"
            hud.parent.mkdir(parents=True)
            hud.write_text("--!strict\nlocal x = 1\n", encoding="utf-8")
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "client_programmer",
                    task,
                    prior_snapshot="--!strict\nlocal x = 1\n",
                    prompt_budget_tokens=3000,
                )
            self.assertNotIn("append AFTER this", prompt)
            self.assertNotIn("WRITE MODE = APPEND", prompt)
            self.assertIn("APPEND disabled", prompt)


class TestDuplicateLocalFunctionStillFails(unittest.TestCase):
    def test_duplicate_local_function_fails(self):
        from forge.validator import validate_file

        body = (
            "--!strict\n"
            "local function updateCoins(n: number)\n"
            "\tprint(n)\n"
            "end\n"
            "local function updateCoins(n: number)\n"
            "\tprint(n)\n"
            "end\n"
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "HUD.client.luau"
            p.write_text(body, encoding="utf-8")
            ok, errs = validate_file(p)
            self.assertFalse(ok, errs)
            self.assertTrue(any("duplicate local function" in e for e in errs), errs)

    def test_dup_check_not_soft_disabled(self):
        src = (ROOT / "forge" / "validator.py").read_text(encoding="utf-8")
        self.assertIn('errors.append(\n                "duplicate local function "', src)
        self.assertNotRegex(src, r"#\s*\(.*duplicate local function")


class TestRepairMandatoryFilePinned(unittest.TestCase):
    def test_prompts_constant_matches(self):
        from forge.prompts import MANDATORY_FILE_LINE

        self.assertEqual(MANDATORY_FILE_LINE, MANDATORY_FILE)

    def test_repair_mode_leads_with_mandatory_file(self):
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
            (root / "AGENTS.md").write_text("# A\n", encoding="utf-8")
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n" + task.raw + "\n", encoding="utf-8"
            )
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    task,
                    validator_feedback=MANDATORY_FILE + "\n1. use task.wait\n",
                    repair_draft="local x = 1\n",
                    is_7b=True,
                    prompt_budget_tokens=1000,
                )
            idx = prompt.find("=== REPAIR MODE")
            self.assertGreaterEqual(idx, 0)
            mode_block = prompt[idx : idx + 500]
            self.assertIn(MANDATORY_FILE, mode_block)
            self.assertLess(
                mode_block.find(MANDATORY_FILE),
                mode_block.find("START YOUR REPLY")
                if "START YOUR REPLY" in mode_block
                else len(mode_block),
            )
            after_hdr = mode_block.split("\n", 1)[1]
            self.assertTrue(
                after_hdr.lstrip().startswith(MANDATORY_FILE),
                after_hdr[:200],
            )

    def test_orchestrator_feedback_starts_with_mandatory(self):
        src = (ROOT / "forge" / "orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("MANDATORY_FILE_LINE", src)
        self.assertRegex(
            src,
            r'validator_feedback\s*=\s*\(\s*\n\s*f?"\{MANDATORY_FILE_LINE\}\\n"',
        )


class TestRemotesWaitRuleInStrict(unittest.TestCase):
    def test_remotes_constant(self):
        from forge.prompts import REMOTES_WAIT_RULE

        self.assertEqual(REMOTES_WAIT_RULE, REMOTES_WAIT)

    def _prompt(self, *, local_ollama: bool) -> str:
        from forge.prompts import build_prompt
        from forge.task_parser import Task, WriteMode

        task = Task(
            raw="- [ ] T8 | REWRITE Effects | @client_programmer | -> src/client/Effects.client.luau",
            task_id="T8",
            owner="client_programmer",
            mode=WriteMode.REWRITE,
            target_path="src/client/Effects.client.luau",
            requires_file=True,
            description="REWRITE Effects",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text("# A\n", encoding="utf-8")
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n" + task.raw + "\n", encoding="utf-8"
            )
            backend = "ollama" if local_ollama else "deepseek"
            with patch("forge.llm.backend_name", return_value=backend):
                return build_prompt(
                    root,
                    "client_programmer",
                    task,
                    prompt_budget_tokens=4000 if not local_ollama else 2000,
                )

    def test_remotes_rule_local_and_cloud(self):
        for local in (True, False):
            with self.subTest(local_ollama=local):
                prompt = self._prompt(local_ollama=local)
                self.assertIn(REMOTES_WAIT, prompt)


class TestDecomposeNoAppend(unittest.TestCase):
    def test_decompose_uses_rewrite(self):
        from forge.orchestrator import decompose_task
        from forge.task_parser import Task, WriteMode

        task = Task(
            raw="",
            task_id="T9",
            owner="client_programmer",
            mode=WriteMode.REWRITE,
            target_path="src/client/HUD.client.luau",
            requires_file=True,
            description="REWRITE HUD",
        )
        micros = decompose_task(task)
        joined = "\n".join(micros)
        self.assertNotIn("APPEND", joined)
        self.assertIn("REWRITE", joined)


if __name__ == "__main__":
    unittest.main()
