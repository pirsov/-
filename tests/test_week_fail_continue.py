#!/usr/bin/env python3
"""Week fail → failed_repair continue, 7B repair checklist, --clear-queue."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import state_hub
from forge.orchestrator import Orchestrator, main, mark_tz_failed_repair, run_loop
from forge.prompts import build_prompt, format_validator_checklist
from forge.task_parser import Task, WriteMode, find_pending_tasks


def _seed_week_root(root: Path) -> None:
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / ".forge" / "snapshots").mkdir(parents=True, exist_ok=True)
    (root / "src" / "server" / "Gameplay").mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text(
        "# Agents\n### @gameplay_programmer\nWrite Luau.\n",
        encoding="utf-8",
    )
    (root / "PROJECT_TZ.md").write_text(
        "# LAST_UPDATE: test\n"
        "## AGENT\n"
        "- [ ] T1 | REWRITE Checkpoints | @gameplay_programmer | -> "
        "src/server/Gameplay/Checkpoints.server.luau\n"
        "- [ ] T2 | REWRITE Coins | @gameplay_programmer | -> "
        "src/server/Gameplay/Coins.server.luau\n",
        encoding="utf-8",
    )
    (root / "state.json").write_text(
        json.dumps(
            {
                "pulse": {"cycle": 2, "status": "looping"},
                "done": [{"plugin": "forge.validator"}],
                "task_queue": [
                    {"id": "T1", "status": "ready"},
                    {"id": "T2", "status": "ready"},
                    {"id": "OLD", "status": "in_progress"},
                ],
                "partial": [{"id": "p1"}],
                "open_questions": [],
                "milestone": "keep-me",
            }
        ),
        encoding="utf-8",
    )


_BAD_CP = (
    "--!strict\n"
    'local Players = game:GetService("Players")\n'
    "print(Players)\n"
)


class TestFormatValidatorChecklist(unittest.TestCase):
    def test_numbered_bullets_from_validator_fails(self):
        text = format_validator_checklist(
            [
                "Checkpoints.server.luau missing Humanoid.Died / LoadCharacter handling",
                'Checkpoints teleport must FindFirstChild("Checkpoint"..idx)',
            ]
        )
        self.assertIn("REPAIR CHECKLIST", text)
        self.assertIn("1. Checkpoints.server.luau missing Humanoid.Died", text)
        self.assertIn('2. Checkpoints teleport must FindFirstChild("Checkpoint"..idx)', text)
        self.assertIn("EVERY bullet", text)

    def test_repair_prompt_embeds_checklist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_week_root(root)
            task = Task(
                raw="- [ ] T1 | REWRITE Checkpoints | @gameplay_programmer | -> "
                "src/server/Gameplay/Checkpoints.server.luau",
                task_id="T1",
                owner="gameplay_programmer",
                mode=WriteMode.REWRITE,
                target_path="src/server/Gameplay/Checkpoints.server.luau",
                requires_file=True,
                description="REWRITE Checkpoints",
            )
            checklist = format_validator_checklist(
                [
                    "Checkpoints.server.luau missing Humanoid.Died / LoadCharacter handling",
                    'Checkpoints teleport must FindFirstChild("Checkpoint"..idx)',
                ]
            )
            prompt = build_prompt(
                root,
                "gameplay_programmer",
                task,
                attempt=2,
                validator_feedback="REPAIR your previous draft.\n" + checklist,
                repair_draft=_BAD_CP,
            )
            self.assertIn("REPAIR CHECKLIST", prompt)
            self.assertIn("Humanoid.Died", prompt)
            self.assertIn('FindFirstChild("Checkpoint"..idx)', prompt)
            self.assertIn("REPAIR MODE (A15 PATCH / 7B)", prompt)
            self.assertIn("bullet-by-bullet", prompt)


class TestFailedRepairContinue(unittest.TestCase):
    def test_mark_tz_failed_repair_skips_pending(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_week_root(root)
            mark_tz_failed_repair(root, "T1", "parked")
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("- [-] T1", tz)
            self.assertIn("FAILED_REPAIR", tz)
            self.assertIn("- [ ] T2", tz)
            pending = find_pending_tasks(tz)
            self.assertEqual([t.task_id for t in pending], ["T2"])

    def test_week_fail_records_open_questions_and_continues_loop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_week_root(root)
            # Always-invalid body → 3 validator fails → failed_repair
            bad = (
                "<DONE>T1</DONE>\n<NOTE>bad</NOTE>\n"
                '<FILE path="src/server/Gameplay/Checkpoints.server.luau">\n'
                f"{_BAD_CP}</FILE>\n"
            )
            good_t2 = (
                "<DONE>T2</DONE>\n<NOTE>ok</NOTE>\n"
                '<FILE path="src/server/Gameplay/Coins.server.luau">\n'
                "--!strict\n"
                'local Players = game:GetService("Players")\n'
                "print(Players)\n"
                "</FILE>\n"
            )
            # Coins validator is loose enough for this stub body
            with patch("forge.orchestrator.validate_file", side_effect=self._validate_side):
                completed = run_loop(
                    root,
                    max_steps=4,
                    sleep_s=0,
                    mock_responses={
                        "T1": [bad, bad, bad],
                        "T2": [good_t2],
                    },
                )
            self.assertGreaterEqual(completed, 1)
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("- [-] T1", tz)
            self.assertIn("- [x] T2", tz)
            st = state_hub.load_state(root)
            oq = st.get("open_questions") or []
            fr = next(q for q in oq if isinstance(q, dict) and q.get("task_id") == "T1")
            self.assertEqual(fr.get("status"), "failed_repair")
            self.assertTrue(fr.get("validator_fails"))
            entry = next(t for t in st["task_queue"] if t["id"] == "T1")
            self.assertEqual(entry["status"], "failed_repair")

    @staticmethod
    def _validate_side(path: Path):
        name = path.name
        if name == "Checkpoints.server.luau":
            return False, [
                "Checkpoints.server.luau missing Humanoid.Died / LoadCharacter handling",
                'Checkpoints teleport must FindFirstChild("Checkpoint"..idx)',
            ]
        return True, []

    def test_invoke_step_failed_repair_reason(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_week_root(root)
            bad = (
                "<DONE>T1</DONE>\n<NOTE>bad</NOTE>\n"
                '<FILE path="src/server/Gameplay/Checkpoints.server.luau">\n'
                f"{_BAD_CP}</FILE>\n"
            )
            orch = Orchestrator(
                root,
                mock_responses={"T1": [bad, bad, bad]},
            )
            with patch("forge.orchestrator.validate_file", return_value=(False, ["missing Humanoid.Died"])):
                result = orch.invoke_step()
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "failed_repair")
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("- [-] T1", tz)
            # Next pending is T2 — loop would continue
            self.assertEqual(orch.next_task().task_id, "T2")


class TestClearQueue(unittest.TestCase):
    def test_clear_queue_keeps_pulse_and_done(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_week_root(root)
            report = state_hub.clear_queue(root)
            self.assertTrue(report["ok"])
            self.assertEqual(report["cleared"], 3)
            self.assertEqual(report["queue_len"], 0)
            st = state_hub.load_state(root)
            self.assertEqual(st["task_queue"], [])
            self.assertEqual(st["partial"], [])
            self.assertEqual(st["pulse"]["cycle"], 2)
            self.assertEqual(st.get("milestone"), "keep-me")
            self.assertEqual(len(st.get("done") or []), 1)
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("- [ ] T1", tz)

    def test_cli_clear_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_week_root(root)
            code = main(["--root", str(root), "--clear-queue"])
            self.assertEqual(code, 0)
            st = state_hub.load_state(root)
            self.assertEqual(st["task_queue"], [])
            self.assertEqual(st["pulse"]["cycle"], 2)


if __name__ == "__main__":
    unittest.main()
