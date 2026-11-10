#!/usr/bin/env python3
"""A17/A25 Hard Context Fit — prompt budgets, num_ctx caps, no oversized Ollama prompts."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from forge import llm_backends
from forge.prompts import AGENT_MODELS, build_prompt, compress_tz_for_prompt, format_validator_checklist
from forge.task_parser import Task, WriteMode


class TestNumCtxCaps(unittest.TestCase):
    def test_local_default_and_max_ctx(self):
        self.assertEqual(llm_backends.LOCAL_NUM_CTX, 2048)
        self.assertEqual(llm_backends.MAX_NUM_CTX, 4096)
        self.assertEqual(llm_backends.cap_num_ctx(4096), 4096)
        self.assertEqual(llm_backends.cap_num_ctx(99999), 4096)
        self.assertEqual(llm_backends.cap_num_ctx(2048), 2048)
        opts = llm_backends.ollama_options(num_ctx=4096, num_predict=1024)
        self.assertEqual(opts["num_ctx"], 4096)
        self.assertLessEqual(opts["num_predict"], 1024)

    def test_agent_models_ctx(self):
        for role in ("gameplay_programmer", "client_programmer"):
            cfg = AGENT_MODELS[role]
            self.assertEqual(int(cfg.get("ctx") or 0), 4096, msg=f"{role} ctx must be 4096")
            self.assertEqual(int(cfg.get("num_ctx") or cfg.get("ctx") or 0), 4096)
        for role, cfg in AGENT_MODELS.items():
            self.assertLessEqual(
                int(cfg.get("ctx") or 0),
                4096,
                msg=f"{role} ctx must be ≤4096",
            )


class TestHardPromptBudgets(unittest.TestCase):
    def test_strict_caps(self):
        self.assertEqual(llm_backends.HARD_PROMPT_TOKENS_14B, 3000)
        self.assertEqual(llm_backends.HARD_PROMPT_TOKENS_7B, 1000)

    def test_effective_budget_leaves_room_for_predict(self):
        # ctx=2048, predict=1024 → prompt room ≈ 992 (room-limited under STRICT 3000)
        b14_default = llm_backends.effective_prompt_token_budget(
            is_7b=False, num_ctx=2048, num_predict=1024
        )
        self.assertLessEqual(b14_default, 3000)
        self.assertLessEqual(b14_default, 2048 - 1024)
        self.assertGreaterEqual(b14_default, 256)

        # A25: gameplay/client ctx=4096 → budget ≈ 3000
        b14 = llm_backends.effective_prompt_token_budget(
            is_7b=False, num_ctx=4096, num_predict=1024
        )
        self.assertEqual(b14, 3000)
        self.assertLessEqual(b14, 4096 - 1024)

        b7 = llm_backends.effective_prompt_token_budget(
            is_7b=True, num_ctx=2048, num_predict=512, diff_mode=True
        )
        self.assertLessEqual(b7, 1000)
        self.assertLessEqual(b7, 2048 - 512)

    def test_fit_prompt_never_over_budget(self):
        fat = "=== AGENTS.md ===\n" + ("x" * 20000) + "\n=== YOUR TASK ===\n- [ ] T1 do thing\n"
        budget = 500
        out, meta = llm_backends.fit_prompt(fat, budget)
        self.assertLessEqual(llm_backends.estimate_tokens(out), budget)
        self.assertTrue(meta["ok"])
        self.assertIn("YOUR TASK", out)

    def test_fit_keeps_repair_checklist(self):
        checklist = format_validator_checklist(
            [
                "Checkpoints.server.luau missing Humanoid.Died / LoadCharacter handling",
                'FindFirstChild("Checkpoint"..idx)',
            ]
        )
        fat = (
            "=== AGENTS.md ===\n"
            + ("AGENTWALL\n" * 2000)
            + "\n=== VALIDATOR FEEDBACK (fix ONLY these issues) ===\n"
            + checklist
            + "\n=== REPAIR MODE (A15 PATCH / 7B) ===\n"
            + ("draftline\n" * 500)
            + "\n=== YOUR TASK ===\n- [ ] T1 REWRITE Checkpoints\n"
            + "Format:\n<DONE>T1</DONE>\n"
        )
        budget = llm_backends.HARD_PROMPT_TOKENS_7B
        out, meta = llm_backends.fit_prompt(fat, budget)
        self.assertLessEqual(llm_backends.estimate_tokens(out), budget)
        self.assertIn("REPAIR CHECKLIST", out)
        self.assertIn("Humanoid.Died", out)
        self.assertIn("YOUR TASK", out)


class TestCompressTzAndBuildPrompt(unittest.TestCase):
    def test_compress_tz_drops_done_keeps_open(self):
        tz = "\n".join(
            [
                "# TZ",
                "## Sprint",
                "- [x] A1 done one",
                "- [x] A2 done two",
                "- [ ] B1 open work",
                "- [-] C1 failed_repair park",
            ]
        )
        out = compress_tz_for_prompt(tz, max_chars=400)
        self.assertIn("B1 open", out)
        self.assertIn("done=", out)
        self.assertNotIn("done one", out)

    def test_build_prompt_respects_7b_budget(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text(
                "# Agents\n### @gameplay_programmer\n" + ("rule\n" * 400),
                encoding="utf-8",
            )
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n- [ ] T1 | @gameplay_programmer | REWRITE → src/server/X.luau | fix\n"
                + "\n".join(f"- [x] D{i} done" for i in range(40)),
                encoding="utf-8",
            )
            (root / "src" / "server").mkdir(parents=True)
            (root / "src" / "server" / "X.luau").write_text("local x = 1\n" * 200, encoding="utf-8")
            task = Task(
                task_id="T1",
                owner="gameplay_programmer",
                mode=WriteMode.REWRITE,
                target_path="src/server/X.luau",
                requires_file=True,
                description="REWRITE X",
                raw="- [ ] T1 | @gameplay_programmer | REWRITE → src/server/X.luau | fix",
            )
            budget = llm_backends.effective_prompt_token_budget(
                is_7b=True, num_ctx=2048, num_predict=512, diff_mode=True
            )
            checklist = format_validator_checklist(["missing Humanoid.Died / LoadCharacter"])
            prompt = build_prompt(
                root,
                "gameplay_programmer",
                task,
                attempt=2,
                validator_feedback=checklist,
                repair_draft="local function broken()\nend\n" * 80,
                is_7b=True,
                prompt_budget_tokens=budget,
                num_ctx=2048,
                num_predict=512,
            )
            self.assertLessEqual(llm_backends.estimate_tokens(prompt), budget)
            self.assertLessEqual(llm_backends.estimate_tokens(prompt), 1000)
            self.assertIn("REPAIR CHECKLIST", prompt)
            self.assertIn("Humanoid.Died", prompt)

    def test_build_prompt_14b_under_strict_3000(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text("# Agents\n### @tech_architect\nDo architecture.\n", encoding="utf-8")
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n- [ ] T9 | @tech_architect | CREATE → docs/ARCHITECTURE.md | sketch\n",
                encoding="utf-8",
            )
            task = Task(
                task_id="T9",
                owner="tech_architect",
                mode=WriteMode.CREATE,
                target_path="docs/ARCHITECTURE.md",
                requires_file=True,
                description="CREATE arch",
                raw="- [ ] T9 | @tech_architect | CREATE → docs/ARCHITECTURE.md | sketch",
            )
            budget = llm_backends.effective_prompt_token_budget(
                is_7b=False, num_ctx=4096, num_predict=1024
            )
            prompt = build_prompt(
                root,
                "tech_architect",
                task,
                prompt_budget_tokens=budget,
                num_ctx=4096,
                num_predict=1024,
            )
            self.assertLessEqual(llm_backends.estimate_tokens(prompt), budget)
            self.assertLessEqual(llm_backends.estimate_tokens(prompt), 3000)
            self.assertEqual(budget, 3000)


if __name__ == "__main__":
    unittest.main()
