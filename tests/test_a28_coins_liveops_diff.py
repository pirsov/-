#!/usr/bin/env python3
"""A28 — Coins exact-copy template, Live Ops missing-file REWRITE, ban SEARCH/REPLACE."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import deepseek
from forge.orchestrator import (
    EXPECTED_GAME_FILES,
    live_ops_missing_file_tasks,
    missing_expected_game_files,
    summarize_done_tasks,
    try_live_ops_more_tasks,
)
from forge.prompts import build_prompt, mode_instructions
from forge.task_parser import Task, WriteMode

EXACT_COPY = (
    "Copy this template EXACTLY. Do not modify the structure. "
    "Only change the sound IDs and attribute names if needed."
)
SEARCH_BAN = (
    "NEVER use <<<<<<< SEARCH / ======= / >>>>>>> REPLACE. "
    "This is Cursor diff format and it will be rejected by the parser. "
    "Always output the COMPLETE file content."
)
COINS_PATH = "src/server/Gameplay/Coins.server.luau"


def _coins_task() -> Task:
    return Task(
        raw=(
            f"- [ ] T4 | REWRITE Coins CanTouch coin:Destroy | @gameplay_programmer | "
            f"-> {COINS_PATH}"
        ),
        task_id="T4",
        owner="gameplay_programmer",
        mode=WriteMode.REWRITE,
        target_path=COINS_PATH,
        requires_file=True,
        description="REWRITE Coins CanTouch coin:Destroy",
    )


def _seed_root(root: Path, *, with_coins_tz: bool = True) -> None:
    (root / "AGENTS.md").write_text(
        "# Agents\n### @gameplay_programmer\nWrite Luau.\n",
        encoding="utf-8",
    )
    tz = "# TZ\n"
    if with_coins_tz:
        tz += (
            f"- [ ] T4 | REWRITE Coins | @gameplay_programmer | -> {COINS_PATH}\n"
        )
    (root / "PROJECT_TZ.md").write_text(tz, encoding="utf-8")
    (root / "state.json").write_text("{}", encoding="utf-8")


class TestCoinsExactCopyTemplate(unittest.TestCase):
    def test_coins_prompt_has_exact_copy_instruction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    _coins_task(),
                    prompt_budget_tokens=4000,
                )
            self.assertIn(EXACT_COPY, prompt)
            self.assertIn(COINS_PATH, prompt)
            # Template only pulled when task targets Coins.server.luau
            self.assertIn("=== COINS TEMPLATE", prompt)

    def test_non_coins_task_skips_coins_template(self):
        task = Task(
            raw="- [ ] T5 | REWRITE Void | @gameplay_programmer | -> src/server/Gameplay/Void.server.luau",
            task_id="T5",
            owner="gameplay_programmer",
            mode=WriteMode.REWRITE,
            target_path="src/server/Gameplay/Void.server.luau",
            requires_file=True,
            description="REWRITE Void",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root, with_coins_tz=False)
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n" + task.raw + "\n", encoding="utf-8"
            )
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    task,
                    prompt_budget_tokens=4000,
                )
            self.assertNotIn("=== COINS TEMPLATE", prompt)
            self.assertNotIn(EXACT_COPY, prompt)


class TestLiveOpsMissingExpectedFiles(unittest.TestCase):
    def test_missing_expected_lists_absent_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "src" / "client").mkdir(parents=True)
            (root / "src" / "client" / "HUD.client.luau").write_text(
                "--!strict\n", encoding="utf-8"
            )
            missing = missing_expected_game_files(root)
            self.assertIn("src/server/Gameplay/Coins.server.luau", missing)
            self.assertIn("src/server/Level/Generator.server.luau", missing)
            self.assertIn("src/shared/Gameplay/Remotes.luau", missing)
            self.assertNotIn("src/client/HUD.client.luau", missing)
            self.assertEqual(len(missing), len(EXPECTED_GAME_FILES) - 1)

    def test_live_ops_missing_tasks_are_rewrite_from_template(self):
        missing = [
            "src/server/Level/Generator.server.luau",
            "src/server/Gameplay/Checkpoints.server.luau",
            "src/server/Gameplay/Void.server.luau",
            "src/server/Gameplay/Puzzles.server.luau",
            "src/shared/Gameplay/Remotes.luau",
            "src/server/InitRemotes.server.luau",
            "src/client/Effects.client.luau",
        ]
        lines = live_ops_missing_file_tasks(missing, start_n=13)
        self.assertEqual(len(lines), len(missing))
        self.assertTrue(all("Create from scratch using template" in ln for ln in lines))
        self.assertTrue(all(ln.startswith("- [ ] T") for ln in lines))
        self.assertIn("-> src/server/Level/Generator.server.luau", lines[0])
        self.assertIn("@gameplay_programmer", lines[0])
        # Effects is client
        effects = [ln for ln in lines if "Effects.client.luau" in ln][0]
        self.assertIn("@client_programmer", effects)
        self.assertIn("REWRITE Effects.client.luau:", effects)

    def test_try_live_ops_prioritizes_missing_before_polish(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "logs").mkdir(parents=True)
            (root / ".forge").mkdir(parents=True)
            (root / "src" / "client").mkdir(parents=True)
            (root / "projects" / "game1").mkdir(parents=True)
            (root / ".forge" / "active_project.json").write_text(
                json.dumps({"id": "game1"}), encoding="utf-8"
            )
            (root / "projects" / "game1" / "meta.json").write_text(
                json.dumps({"id": "game1", "title": "Horror coins"}),
                encoding="utf-8",
            )
            # Only HUD present — many EXPECTED_GAME_FILES missing
            (root / "src" / "client" / "HUD.client.luau").write_text(
                "--!strict\n", encoding="utf-8"
            )
            (root / "PROJECT_TZ.md").write_text(
                "# LAST_UPDATE: game1\n\n## AGENT\n"
                "- [x] T1 | REWRITE LevelConfig | @gameplay_programmer | "
                "-> src/shared/Content/LevelConfig.luau\n"
                "- [x] T12 | REWRITE QA | @qa_engineer | -> docs/QA_REPORT.md\n\n"
                "## HUMAN\n- [x] H1 | smoke | @human\n",
                encoding="utf-8",
            )
            polish_batch = (
                "- [ ] T99 | REWRITE Effects coin sound polish | @client_programmer | "
                "-> src/client/Effects.client.luau\n"
                "- [ ] T100 | REWRITE HUD tween flash | @client_programmer | "
                "-> src/client/HUD.client.luau\n"
                "- [ ] T101 | REWRITE Leaderboard juice | @client_programmer | "
                "-> src/client/Leaderboard.client.luau\n"
            )
            with patch.object(deepseek, "available", return_value=True), patch.object(
                deepseek, "chat", return_value=polish_batch
            ) as chat_mock:
                n = try_live_ops_more_tasks(root)
            self.assertGreater(n, 0)
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            # Missing-file REWRITE tasks present
            self.assertIn("Create from scratch using template", tz)
            self.assertIn("-> src/server/Gameplay/Coins.server.luau", tz)
            self.assertIn("-> src/server/Level/Generator.server.luau", tz)
            self.assertIn("-> src/shared/Gameplay/Remotes.luau", tz)
            self.assertIn("-> src/server/InitRemotes.server.luau", tz)
            # First AGENT pending task is a missing-file REWRITE, not polish
            pending = [
                ln
                for ln in tz.splitlines()
                if ln.startswith("- [ ] T")
            ]
            self.assertTrue(pending)
            self.assertIn("Create from scratch using template", pending[0])
            # With many missing files, polish DeepSeek must NOT run this round
            chat_mock.assert_not_called()
            self.assertNotIn("T99", tz)
            self.assertNotIn("coin sound polish", tz)


class TestStrictBanSearchReplace(unittest.TestCase):
    def test_strict_rules_ban_search_replace_markers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    _coins_task(),
                    prompt_budget_tokens=4000,
                )
            self.assertIn(SEARCH_BAN, prompt)
            # Format example must not teach Cursor diff markers
            self.assertNotIn("<<<<<<< SEARCH\nold lines", prompt)

    def test_mode_instructions_forbid_search_replace(self):
        task = Task(
            task_id="T1",
            description="fix coins",
            owner="gameplay_programmer",
            target_path=COINS_PATH,
            mode=WriteMode.REWRITE,
            raw="- [ ] T1 | REWRITE",
            requires_file=True,
            section=None,
        )
        text = mode_instructions(task, file_exists=True, prefer_diff=True)
        self.assertIn("COMPLETE", text)
        self.assertIn("NEVER use <<<<<<< SEARCH", text)
        self.assertNotIn("Prefer SEARCH/REPLACE blocks", text)


if __name__ == "__main__":
    unittest.main()
