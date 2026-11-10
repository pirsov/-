#!/usr/bin/env python3
"""A20.0 Live Ops: invent more TZ tasks when --week queue is empty."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from forge import deepseek
from forge.orchestrator import (
    append_tz_tasks_before_human,
    run_loop,
    summarize_done_tasks,
    try_live_ops_more_tasks,
)


_DONE_TZ = """# LAST_UPDATE: game1 live ops test
# Goal: polish horror coins obstacle

## AGENT
- [x] T1 | REWRITE LevelConfig | @gameplay_programmer | -> src/shared/Content/LevelConfig.luau
- [x] T2 | REWRITE Generator | @gameplay_programmer | -> src/server/Level/Generator.server.luau
- [x] T12 | REWRITE QA_REPORT | @qa_engineer | -> docs/QA_REPORT.md

## HUMAN
- [x] H1 | Studio smoke | @human
"""

_NEW_BATCH = """
- [ ] T13 | REWRITE Effects coin sound volume + pcall | @client_programmer | -> src/client/Effects.client.luau
- [ ] T14 | APPEND GDD polish notes juice | @game_designer | -> docs/GDD.md#polish
- [ ] T15 | REWRITE HUD tween Best flash | @client_programmer | -> src/client/HUD.client.luau
- [ ] T16 | REWRITE Coins opt touch debounce | @gameplay_programmer | -> src/server/Gameplay/Coins.server.luau
"""


def _seed_empty_queue(root: Path) -> None:
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / ".forge").mkdir(parents=True, exist_ok=True)
    (root / "src" / "client").mkdir(parents=True, exist_ok=True)
    (root / "src" / "server" / "Gameplay").mkdir(parents=True, exist_ok=True)
    (root / "projects" / "game1").mkdir(parents=True, exist_ok=True)
    (root / ".forge" / "active_project.json").write_text(
        json.dumps({"id": "game1"}), encoding="utf-8"
    )
    (root / "projects" / "game1" / "meta.json").write_text(
        json.dumps(
            {
                "id": "game1",
                "title": "Horror coins",
                "skills_auto_goal": "polish sound opt HUD juice",
            }
        ),
        encoding="utf-8",
    )
    (root / "src" / "client" / "HUD.client.luau").write_text("--!strict\n", encoding="utf-8")
    (root / "PROJECT_TZ.md").write_text(_DONE_TZ, encoding="utf-8")
    (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (root / "state.json").write_text(
        json.dumps({"pulse": {"cycle": 1, "status": "looping"}, "task_queue": [], "done": []}),
        encoding="utf-8",
    )


class TestGenerateMoreTasks(unittest.TestCase):
    def test_next_id_continues_from_summary(self):
        self.assertEqual(deepseek.next_tz_task_number("T1 T12 done"), 13)
        self.assertEqual(deepseek.next_tz_task_number(""), 13)
        self.assertEqual(deepseek.next_tz_task_number("- [x] T20 | x | @qa | -> docs/x.md"), 21)

    def test_generate_more_tasks_mocked(self):
        with patch.object(deepseek, "available", return_value=True), patch.object(
            deepseek, "chat", return_value=_NEW_BATCH
        ) as chat_mock:
            lines = deepseek.generate_more_tasks(
                "game1",
                "polish sound opt",
                ["src/client/HUD.client.luau"],
                summarize_done_tasks(_DONE_TZ),
            )
        self.assertGreaterEqual(len(lines), 3)
        self.assertLessEqual(len(lines), 5)
        self.assertTrue(all(ln.startswith("- [ ] T1") for ln in lines))
        self.assertIn("T13", lines[0])
        chat_mock.assert_called_once()
        # prompt must mention continuing ids
        user_prompt = chat_mock.call_args[0][0]
        self.assertIn("T13", user_prompt)

    def test_generate_more_tasks_empty_without_key(self):
        with patch.object(deepseek, "available", return_value=False):
            self.assertEqual(
                deepseek.generate_more_tasks("game1", "g", [], "T1 done"),
                [],
            )

    def test_generate_filters_duplicate_ids(self):
        dup = (
            "- [ ] T12 | REWRITE QA again | @qa_engineer | -> docs/QA_REPORT.md\n"
            "- [ ] T13 | REWRITE Effects | @client_programmer | -> src/client/Effects.client.luau\n"
            "- [ ] T14 | REWRITE HUD | @client_programmer | -> src/client/HUD.client.luau\n"
            "- [ ] T15 | APPEND GDD | @game_designer | -> docs/GDD.md#x\n"
        )
        with patch.object(deepseek, "available", return_value=True), patch.object(
            deepseek, "chat", return_value=dup
        ):
            lines = deepseek.generate_more_tasks(
                "game1", "g", [], summarize_done_tasks(_DONE_TZ)
            )
        ids = [ln.split("|", 1)[0].strip().split()[-1] for ln in lines]
        self.assertNotIn("T12", ids)
        self.assertGreaterEqual(len(lines), 3)

    def test_too_few_lines_returns_empty(self):
        with patch.object(deepseek, "available", return_value=True), patch.object(
            deepseek, "chat", return_value="- [ ] T13 | REWRITE X | @client_programmer | -> src/client/HUD.client.luau\n"
        ):
            self.assertEqual(
                deepseek.generate_more_tasks("game1", "g", [], "T12 done"),
                [],
            )


class TestAppendBeforeHuman(unittest.TestCase):
    def test_append_inserts_before_human(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "PROJECT_TZ.md").write_text(_DONE_TZ, encoding="utf-8")
            n = append_tz_tasks_before_human(
                root,
                [
                    "- [ ] T13 | REWRITE Effects | @client_programmer | -> src/client/Effects.client.luau",
                    "- [ ] T14 | REWRITE HUD | @client_programmer | -> src/client/HUD.client.luau",
                    "- [ ] T15 | APPEND GDD | @game_designer | -> docs/GDD.md#x",
                ],
            )
            self.assertEqual(n, 3)
            text = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            agent_i = text.index("## AGENT")
            t13_i = text.index("T13")
            human_i = text.index("## HUMAN")
            self.assertLess(agent_i, t13_i)
            self.assertLess(t13_i, human_i)
            self.assertIn("H1", text)


class TestLiveOpsRunLoop(unittest.TestCase):
    def test_week_no_tasks_generates_and_continues(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_empty_queue(root)
            # After Live Ops appends T13.., mock completes first new task then stop via max_steps
            good = (
                "<DONE>T13</DONE>\n<NOTE>ok</NOTE>\n"
                '<FILE path="src/client/Effects.client.luau">\n'
                "--!strict\nprint(1)\n</FILE>\n"
            )
            with patch("forge.deepseek.available", return_value=True), patch(
                "forge.deepseek.chat", return_value=_NEW_BATCH
            ), patch(
                "forge.orchestrator.validate_file", return_value=(True, [])
            ), redirect_stdout(io.StringIO()) as buf:
                completed = run_loop(
                    root,
                    max_steps=2,
                    sleep_s=0,
                    week=True,
                    mock_responses={"T13": [good]},
                )
            out = buf.getvalue()
            self.assertIn("[Live Ops] Tasks exhausted. Generated", out)
            self.assertIn("Continuing.", out)
            # ASCII-safe: no fancy dashes/arrows required in Live Ops line
            self.assertNotIn("…", out)
            self.assertNotIn("→", out.split("[Live Ops]")[1].split("\n")[0] if "[Live Ops]" in out else "")
            self.assertGreaterEqual(completed, 1)
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("T13", tz)
            self.assertIn("T14", tz)
            # still before HUMAN
            self.assertLess(tz.index("T14"), tz.index("## HUMAN"))

    def test_week_stops_after_three_empty_batches(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_empty_queue(root)
            with patch("forge.deepseek.available", return_value=True), patch(
                "forge.deepseek.chat", return_value="nope not tasks"
            ), redirect_stdout(io.StringIO()) as buf:
                completed = run_loop(
                    root,
                    max_steps=10,
                    sleep_s=0,
                    week=True,
                )
            out = buf.getvalue()
            self.assertEqual(completed, 0)
            self.assertIn("[Live Ops] DeepSeek could not invent new tasks. Stopping.", out)
            self.assertEqual(out.count("empty/duplicate batch"), 2)  # 1/3 and 2/3 before stop

    def test_non_week_still_stops_on_no_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_empty_queue(root)
            with patch("forge.deepseek.generate_more_tasks") as gen, redirect_stdout(
                io.StringIO()
            ):
                completed = run_loop(root, max_steps=5, sleep_s=0, week=False)
            gen.assert_not_called()
            self.assertEqual(completed, 0)

    def test_try_live_ops_rejects_all_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_empty_queue(root)
            # Model returns only already-done T12-style dupes + ids that append filters
            dup_batch = (
                "- [ ] T12 | REWRITE QA_REPORT | @qa_engineer | -> docs/QA_REPORT.md\n"
                "- [ ] T1 | REWRITE LevelConfig | @gameplay_programmer | -> src/shared/Content/LevelConfig.luau\n"
                "- [ ] T2 | REWRITE Generator | @gameplay_programmer | -> src/server/Level/Generator.server.luau\n"
            )
            with patch("forge.deepseek.available", return_value=True), patch(
                "forge.deepseek.chat", return_value=dup_batch
            ):
                # generate_more_tasks itself returns [] (<3 fresh)
                self.assertEqual(try_live_ops_more_tasks(root), 0)


if __name__ == "__main__":
    unittest.main()
