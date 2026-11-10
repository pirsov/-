#!/usr/bin/env python3
"""A26 — duplicate local function FAIL, LocalPlayer server STRICT, Coins MUST, repair FILE pin."""
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
LOCALPLAYER_SERVER_RULE = (
    "NEVER use LocalPlayer in .server.luau files. LocalPlayer is client-only. "
    "Use Players.PlayerAdded or GetPlayerFromCharacter."
)
COINS_MUST_GET_PLAYER = (
    "You MUST use Players:GetPlayerFromCharacter(char) to find the player."
)
COINS_MUST_DESTROY_LB = (
    "You MUST call coin:Destroy() and FireAllClients UpdateLeaderboard."
)


class TestDuplicateLocalFunctionFail(unittest.TestCase):
    def test_duplicate_local_function_fails(self):
        from forge.validator import validate_file

        body = (
            "--!strict\n"
            "local Players = game:GetService(\"Players\")\n"
            "local function updateCoins(n: number)\n"
            "\tprint(n)\n"
            "end\n"
            "local function updateCheckpoint(idx: number)\n"
            "\tprint(idx)\n"
            "end\n"
            "local function updateCoins(n: number)\n"
            "\tprint(\"dup\", n)\n"
            "end\n"
            "local function updateCheckpoint(idx: number)\n"
            "\tprint(\"dup\", idx)\n"
            "end\n"
            "print(\"HUD append paste\")\n"
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "HUD.client.luau"
            p.write_text(body, encoding="utf-8")
            ok, errs = validate_file(p)
            self.assertFalse(ok, errs)
            joined = "\n".join(errs)
            self.assertIn("duplicate local function", joined)
            self.assertIn("updateCoins", joined)
            self.assertIn("updateCheckpoint", joined)

    def test_unique_local_functions_ok(self):
        from forge.validator import validate_file

        body = (
            "--!strict\n"
            "local Players = game:GetService(\"Players\")\n"
            "local player = Players.LocalPlayer\n"
            "local Remotes = require(game.ReplicatedStorage.Gameplay.Remotes)\n"
            "local function updateCoins(n: number)\n"
            "\tprint(n)\n"
            "end\n"
            "local function updateCheckpoint(idx: number)\n"
            "\tprint(idx)\n"
            "end\n"
            "Remotes.CoinCollected.OnClientEvent:Connect(updateCoins)\n"
            "Remotes.CheckpointReached.OnClientEvent:Connect(updateCheckpoint)\n"
            "local gui = Instance.new(\"ScreenGui\")\n"
            "gui.Parent = player:WaitForChild(\"PlayerGui\")\n"
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "HUD.client.luau"
            p.write_text(body, encoding="utf-8")
            ok, errs = validate_file(p)
            self.assertFalse(
                any("duplicate local function" in e for e in errs),
                errs,
            )

    def test_dup_check_not_in_soft_temp_set(self):
        """A22.1 soft mode must NOT disable duplicate-function structural check."""
        src = (ROOT / "forge" / "validator.py").read_text(encoding="utf-8")
        # Soft TEMP comments exist for BreakJoints / Checkpoint part / DataStore —
        # duplicate local function block must remain active (not commented).
        self.assertIn("duplicate local function", src)
        self.assertNotRegex(
            src,
            r"#\s*\(.*duplicate local function",
        )
        # Ensure the active append message is present as live code, not only a comment.
        self.assertIn(
            'errors.append(\n                "duplicate local function "',
            src,
        )


class TestLocalPlayerServerRuleInPrompt(unittest.TestCase):
    def _prompt_for(self, target: str, *, local_ollama: bool) -> str:
        from forge.prompts import build_prompt
        from forge.task_parser import Task, WriteMode

        task = Task(
            raw=f"- [ ] T3 | REWRITE Checkpoints | @gameplay_programmer | -> {target}",
            task_id="T3",
            owner="gameplay_programmer",
            mode=WriteMode.REWRITE,
            target_path=target,
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
            backend = "ollama" if local_ollama else "deepseek"
            with patch("forge.llm.backend_name", return_value=backend):
                return build_prompt(
                    root,
                    "gameplay_programmer",
                    task,
                    prompt_budget_tokens=4000 if not local_ollama else 2000,
                )

    def test_strict_rules_ban_localplayer_on_server(self):
        for local in (False, True):
            with self.subTest(local_ollama=local):
                prompt = self._prompt_for(
                    "src/server/Gameplay/Checkpoints.server.luau",
                    local_ollama=local,
                )
                self.assertIn(LOCALPLAYER_SERVER_RULE, prompt)
                self.assertIn("STRICT", prompt)

    def test_checkpoints_covered_by_server_rule(self):
        prompt = self._prompt_for(
            "src/server/Gameplay/Checkpoints.server.luau",
            local_ollama=False,
        )
        self.assertIn(LOCALPLAYER_SERVER_RULE, prompt)
        self.assertIn("GetPlayerFromCharacter", prompt)


class TestCoinsMustStrings(unittest.TestCase):
    def test_coins_must_get_player_and_destroy_leaderboard(self):
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
            self.assertIn(COINS_MUST_GET_PLAYER, prompt)
            self.assertIn(COINS_MUST_DESTROY_LB, prompt)
            self.assertIn("FireAllClients", prompt)
            self.assertIn("UpdateLeaderboard", prompt)


class TestRepairMandatoryFileAtTop(unittest.TestCase):
    def test_repair_mode_starts_with_mandatory(self):
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
            mode_block = prompt[idx_mode : idx_mode + 700]
            # First content line after header must be MANDATORY
            after_header = mode_block.split("\n", 1)[1]
            self.assertTrue(
                after_header.lstrip().startswith("MANDATORY:"),
                after_header[:200],
            )
            self.assertIn(MANDATORY_FILE, mode_block)
            self.assertLess(
                mode_block.find(MANDATORY_FILE),
                mode_block.find("START YOUR REPLY WITH <DONE>"),
            )

    def test_orchestrator_repair_feedback_mandatory_first(self):
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
            first = captured[0].lstrip()
            self.assertTrue(
                first.startswith("MANDATORY:"),
                first[:240],
            )
            self.assertIn(MANDATORY_FILE, first)
            self.assertLess(
                first.find(MANDATORY_FILE),
                first.find("START YOUR REPLY WITH <DONE>"),
            )

    def test_fit_prompt_keeps_mandatory_line(self):
        from forge import llm_backends

        huge = "=== AGENTS.md ===\n" + ("x" * 8000) + "\n"
        repair = (
            "=== REPAIR MODE (A15 PATCH / 7B) ===\n"
            f"{MANDATORY_FILE}\n"
            "MANDATORY FILE TAG — do not omit; replies without <FILE> are rejected.\n"
            "START YOUR REPLY WITH <DONE>T3</DONE>. DO NOT FORGET THE XML TAGS.\n"
            "draft fluff\n" + ("y" * 4000) + "\n"
        )
        prompt = huge + repair + "=== YOUR TASK ===\nfix it\n"
        fitted, meta = llm_backends.fit_prompt(prompt, 400)
        self.assertIn("MANDATORY:", fitted)
        self.assertIn("<FILE", fitted)
        self.assertTrue(meta.get("ok") or "MANDATORY" in fitted)


if __name__ == "__main__":
    unittest.main()
