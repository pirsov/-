#!/usr/bin/env python3
"""A19.0 - HARD CAPS in prompts + CRITICAL HUD character:GetAttribute fail."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


class TestHardCapsInPrompt(unittest.TestCase):
    def test_strict_rules_include_hard_caps(self):
        from forge.prompts import build_prompt
        from forge.task_parser import Task, WriteMode

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text("# Agents\n### @gameplay_programmer\nx\n", encoding="utf-8")
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n- [ ] H1 | @gameplay_programmer | REWRITE -> src/client/HUD.client.luau | hud\n",
                encoding="utf-8",
            )
            task = Task(
                raw="- [ ] H1 | REWRITE HUD | @gameplay_programmer | -> src/client/HUD.client.luau",
                task_id="H1",
                owner="gameplay_programmer",
                mode=WriteMode.REWRITE,
                target_path="src/client/HUD.client.luau",
                requires_file=True,
                description="REWRITE HUD",
            )
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    task,
                    prompt_budget_tokens=4000,
                )
            self.assertIn("HARD CAPS", prompt)
            self.assertIn('NEVER use character:GetAttribute("Coins")', prompt)
            self.assertIn("ALWAYS use player:GetAttribute(\"Coins\")", prompt)
            self.assertIn("NEVER use Remotes.CoinsCollected", prompt)
            self.assertIn("Remotes.CoinCollected", prompt)
            self.assertIn("NEVER destroy Coins in Checkpoints.server.luau", prompt)
            self.assertIn('Instance.new("SpawnLocation")', prompt)
            self.assertIn('NEVER use Instance.new("Part")', prompt)


class TestHudCharacterGetAttributeCritical(unittest.TestCase):
    def _write_hud(self, td: str, body: str) -> Path:
        p = Path(td) / "HUD.client.luau"
        p.write_text(
            "--!strict\n"
            "local Players = game:GetService(\"Players\")\n"
            "local player = Players.LocalPlayer\n"
            "local Remotes = require(game.ReplicatedStorage.Gameplay.Remotes)\n"
            "local gui = Instance.new(\"ScreenGui\")\n"
            "local label = Instance.new(\"TextLabel\")\n"
            "Remotes.CheckpointReached.OnClientEvent:Connect(function() end)\n"
            "Remotes.CoinCollected.OnClientEvent:Connect(function() end)\n"
            + body,
            encoding="utf-8",
        )
        return p

    def test_character_getattribute_coins_fails_task(self):
        from forge.validator import validate_file

        with tempfile.TemporaryDirectory() as td:
            p = self._write_hud(
                td,
                'local character = player.Character\n'
                'local coins = character:GetAttribute("Coins") or 0\n',
            )
            ok, errs = validate_file(p)
            self.assertFalse(ok, "character:GetAttribute must FAIL the task")
            joined = " ".join(errs)
            self.assertIn("CRITICAL", joined)
            self.assertIn("character:GetAttribute", joined)

    def test_char_getattribute_any_attr_fails(self):
        from forge.validator import validate_file

        with tempfile.TemporaryDirectory() as td:
            p = self._write_hud(
                td,
                'local char = player.Character\n'
                'local n = char:GetAttribute("Score")\n',
            )
            ok, errs = validate_file(p)
            self.assertFalse(ok)
            self.assertTrue(any("CRITICAL" in e for e in errs), errs)

    def test_player_getattribute_passes(self):
        from forge.validator import validate_file

        with tempfile.TemporaryDirectory() as td:
            p = self._write_hud(
                td,
                'local coins = player:GetAttribute("Coins") or 0\n'
                'local cp = player:GetAttribute("Checkpoint") or 0\n',
            )
            ok, errs = validate_file(p)
            self.assertTrue(ok, errs)


class TestWeekPrintsQualityScore(unittest.TestCase):
    def test_week_start_prints_quality_score(self):
        from forge import orchestrator as orch

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text("# a\n", encoding="utf-8")
            (root / "PROJECT_TZ.md").write_text("# TZ\n", encoding="utf-8")
            (root / "state.json").write_text("{}", encoding="utf-8")
            (root / "logs").mkdir(parents=True, exist_ok=True)

            buf = io.StringIO()
            with patch.object(orch, "run_loop", return_value=0), patch.object(
                orch.llm, "reset_runtime_backend"
            ), patch.object(
                orch.llm, "resolve_runtime_backend", return_value=("stub", "test")
            ), patch.object(
                orch, "quality_score", return_value=(72, ["note-a", "note-b"])
            ), redirect_stdout(buf):
                code = orch.main(
                    [
                        "--week",
                        "--max",
                        "0",
                        "--sleep",
                        "0",
                        "--dry-run",
                        "--root",
                        str(root),
                    ]
                )
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertIn("WEEK MODE", out)
            self.assertIn("Quality score: 72/100", out)
            week_idx = out.find("Quality score: 72/100")
            final_idx = out.find("Final quality score")
            self.assertGreaterEqual(week_idx, 0)
            if final_idx >= 0:
                self.assertLess(week_idx, final_idx)


if __name__ == "__main__":
    unittest.main()
