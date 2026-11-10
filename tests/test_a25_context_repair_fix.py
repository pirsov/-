#!/usr/bin/env python3
"""A25.0 — Context & Repair Fix (user A23.0): 14B ctx 4096 / budget~3000, repair FILE, Coins MUST."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent

MANDATORY_FILE = (
    'MANDATORY: Your reply MUST contain <FILE path="...">...</FILE>. '
    "If you don't include the FILE tag, your fix will be rejected."
)
COINS_MUST = (
    "You MUST use Players:GetPlayerFromCharacter(char). "
    "You MUST call coin:Destroy(). You MUST use task.wait()."
)


class TestNumCtx4096Roles(unittest.TestCase):
    def test_models_json_gameplay_client_4096(self):
        from forge.prompts import AGENT_MODELS, load_model_config

        cfg = load_model_config()
        for role in ("gameplay_programmer", "client_programmer"):
            agent = (cfg.get("agents") or {})[role]
            self.assertEqual(int(agent["ctx"]), 4096, role)
            self.assertEqual(int(agent.get("num_ctx") or agent["ctx"]), 4096, role)
            self.assertEqual(int(AGENT_MODELS[role]["ctx"]), 4096, role)

    def test_pick_model_passes_4096_to_budget(self):
        from forge import llm_backends
        from forge.orchestrator import pick_model

        with patch("forge.orchestrator.llm.backend_name", return_value="ollama"), patch(
            "forge.orchestrator.installed_models", return_value=["qwen2.5-coder:14b-4k"]
        ), patch("forge.orchestrator.llm.resolve_model", side_effect=lambda p, *a, **k: p):
            cfg = pick_model("gameplay_programmer", attempt=1, escalate=False)
        self.assertEqual(int(cfg["ctx"]), 4096)
        self.assertEqual(int(cfg.get("num_ctx") or cfg["ctx"]), 4096)
        self.assertGreaterEqual(int(cfg["prompt_budget_tokens"]), 2900)
        self.assertLessEqual(int(cfg["prompt_budget_tokens"]), 3000)
        opts = llm_backends.ollama_options(num_ctx=cfg["ctx"], num_predict=cfg["predict"])
        self.assertEqual(opts["num_ctx"], 4096)

    def test_ollama_options_pass_4096(self):
        from forge import llm_backends

        opts = llm_backends.ollama_options(num_ctx=4096, num_predict=1024)
        self.assertEqual(opts["num_ctx"], 4096)
        self.assertEqual(llm_backends.cap_num_ctx(4096), 4096)
        self.assertEqual(llm_backends.MAX_NUM_CTX, 4096)


class TestBudget3000For14B(unittest.TestCase):
    def test_hard_cap_and_effective_budget(self):
        from forge import llm_backends

        self.assertEqual(llm_backends.HARD_PROMPT_TOKENS_14B, 3000)
        self.assertEqual(llm_backends.HARD_PROMPT_TOKENS_7B, 1000)
        b = llm_backends.effective_prompt_token_budget(
            is_7b=False, num_ctx=4096, num_predict=1024
        )
        self.assertEqual(b, 3000)
        # 7B stays room-limited / ≤1000
        b7 = llm_backends.effective_prompt_token_budget(
            is_7b=True, num_ctx=2048, num_predict=512, diff_mode=True
        )
        self.assertLessEqual(b7, 1000)


class TestRepairMandatoryFile(unittest.TestCase):
    def test_repair_mode_block_starts_with_mandatory(self):
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
            idx_mode = prompt.find("=== REPAIR MODE")
            self.assertGreaterEqual(idx_mode, 0)
            mode_block = prompt[idx_mode : idx_mode + 500]
            self.assertIn(MANDATORY_FILE, mode_block)
            # MANDATORY must appear before the DONE reminder inside REPAIR MODE
            self.assertLess(
                mode_block.find(MANDATORY_FILE),
                mode_block.find("START YOUR REPLY WITH <DONE>"),
            )
            self.assertIn(
                'You MUST include <FILE path="...">content</FILE>. The FILE tag is mandatory.',
                mode_block,
            )

    def test_orchestrator_repair_feedback_has_mandatory(self):
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
            self.assertTrue(
                joined.lstrip().startswith(MANDATORY_FILE)
                or MANDATORY_FILE in joined,
                joined[:400],
            )
            self.assertLess(
                joined.find(MANDATORY_FILE),
                joined.find("START YOUR REPLY WITH <DONE>"),
            )


class TestCoinsMustRules(unittest.TestCase):
    def test_coins_block_has_must_rules(self):
        from forge.prompts import build_prompt
        from forge.task_parser import Task, WriteMode

        task = Task(
            raw="- [ ] T4 | REWRITE Coins | @gameplay_programmer | -> "
            "src/server/Gameplay/Coins.server.luau",
            task_id="T4",
            owner="gameplay_programmer",
            mode=WriteMode.REWRITE,
            target_path="src/server/Gameplay/Coins.server.luau",
            requires_file=True,
            description="REWRITE Coins",
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
            self.assertIn("=== COINS TEMPLATE", prompt)
            self.assertIn(COINS_MUST, prompt)
            self.assertIn("Players:GetPlayerFromCharacter(char)", prompt)
            self.assertIn("coin:Destroy()", prompt)
            self.assertIn("task.wait()", prompt)


if __name__ == "__main__":
    unittest.main()
