#!/usr/bin/env python3
"""A9.0 api_hub tests — planner/feedback mocked, no Ollama/DeepSeek."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import api_hub, run_hub


SAMPLE_PACK = {
    "kind": "hitl_pack",
    "cycle": 1,
    "questions": [
        {
            "id": "Q1",
            "topic": "donation",
            "ask": "Какой UX доната?",
            "options": [
                {"key": "A", "label": "Кнопки 10/50/100"},
                {"key": "B", "label": "Слайдер"},
                {"key": "C", "label": "Только GamePass"},
            ],
            "other": {"key": "other", "label": "Другое", "allows_text": True},
            "default_if_timeout": "A",
        }
    ],
}


def _reset_run_hub() -> None:
    run_hub._stop_event.clear()
    with run_hub._lock:
        run_hub._state.update(
            {
                "status": "idle",
                "started_at": None,
                "ended_at": None,
                "exit_code": None,
                "pid": None,
                "log_path": None,
                "report": {},
                "mode": None,
                "waiting_reason": None,
                "waiting_detail": None,
                "loop_cycle": 0,
                "loop_max": 0,
                "stop_requested": False,
            }
        )


def _seed_root(root: Path) -> None:
    (root / "state.json").write_text(
        json.dumps(
            {
                "pulse": {"cycle": 3},
                "done": [
                    {"plugin": "game1.hud", "status": "closed_verified"},
                    {"plugin": "game1.coins", "status": "done"},
                ],
                "task_queue": [
                    {"id": "T1", "status": "ready", "title": "donation ui"},
                    {"id": "T2", "status": "done", "title": "old"},
                ],
                "open_questions": [],
            }
        ),
        encoding="utf-8",
    )
    (root / "knowledge_base.json").write_text(
        json.dumps({"rules": [{"id": "R1"}], "plugins": {}}),
        encoding="utf-8",
    )


class TestApiHubStatus(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        _reset_run_hub()

    def test_status_snapshot_counts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            snap = api_hub.status_snapshot(root)
            self.assertTrue(snap["ok"])
            self.assertEqual(snap["plugins_closed"], 2)
            self.assertEqual(snap["plugins_verified"], 1)
            self.assertEqual(snap["queue_pending"], 1)
            self.assertEqual(snap["knowledge_rules"], 1)
            self.assertFalse(snap["waiting_human"])


class TestApiHubChat(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        _reset_run_hub()

    def test_empty_message(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = api_hub.chat(root, message="   ")
            self.assertFalse(out["ok"])

    def test_chat_waiting_human_hitl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)

            def fake_improve(text, project_id="game1", compact_skills=None):
                return {"goal": "donation system with buttons", "skills_hint": ["forge-ui-modern"]}

            def fake_plan(root_arg, focus=""):
                return {"action": "ask_hitl", "pack": SAMPLE_PACK, "cycle": 3}

            with patch("forge.api_hub.deepseek.improve_goal", side_effect=fake_improve), patch(
                "forge.api_hub.planner.plan_next", side_effect=fake_plan
            ), patch("forge.api_hub.deepseek.available", return_value=False):
                out = api_hub.chat(root, message="Сделай систему доната с кнопками")

            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "waiting_human")
            self.assertEqual(out["hitl_pack"]["questions"][0]["id"], "Q1")
            self.assertEqual(run_hub.status()["status"], "waiting_human")
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertIn("last_chat", state)

    def test_chat_verify_plugin_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)

            with patch(
                "forge.api_hub.deepseek.improve_goal",
                return_value={"goal": "check hud", "skills_hint": []},
            ), patch(
                "forge.api_hub.planner.plan_next",
                return_value={
                    "action": "verify_plugin",
                    "plugin": "game1.hud",
                    "hint": "smoke",
                },
            ), patch("forge.api_hub.deepseek.available", return_value=False):
                out = api_hub.chat(root, message="проверь HUD")

            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "waiting_human")
            self.assertEqual(out["verify_plugin"], "game1.hud")
            self.assertEqual(run_hub.status()["waiting_reason"], "verify_plugin")


class TestApiHubAnswer(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        _reset_run_hub()

    def test_answer_hitl_clears_wait(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            run_hub.set_waiting_human(reason="hitl_pack")

            with patch(
                "forge.api_hub.planner.record_hitl_answers",
                return_value={"ok": True, "resolved": {"Q1": {"key": "A"}}, "followups": []},
            ), patch(
                "forge.api_hub.planner.plan_next",
                return_value={"action": "idle", "cycle": 3},
            ):
                out = api_hub.answer(root, answer_str="Q1=A")

            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "answered")
            self.assertNotEqual(run_hub.status()["status"], "waiting_human")

    def test_answer_verify_calls_feedback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            run_hub.set_waiting_human(reason="verify_plugin", detail={"plugin": "game1.hud"})

            with patch(
                "forge.api_hub.feedback.submit_verdict",
                return_value={"status": "closed_verified", "plugin": "game1.hud"},
            ) as mocked:
                out = api_hub.answer(
                    root, channel="verify", plugin="game1.hud", verdict="y", note="ok"
                )

            mocked.assert_called_once()
            self.assertTrue(out["ok"])
            self.assertEqual(out["channel"], "verify")
            self.assertNotEqual(run_hub.status()["status"], "waiting_human")

    def test_answer_requires_payload(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out = api_hub.answer(root, answers={})
            self.assertFalse(out["ok"])


class TestApiHub24h(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        run_hub.stop_24h()
        _reset_run_hub()

    def test_start_and_stop_24h(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)

            with patch(
                "forge.planner.plan_next",
                return_value={"action": "idle", "cycle": 1},
            ), patch(
                "forge.run_hub.start_week",
                return_value={"ok": True, "status": "done"},
            ):
                out = api_hub.start_24h(root, sleep=1.0, max_cycles=1, week_max_steps=1)
                self.assertTrue(out["ok"])
                self.assertIn(out.get("status"), {"looping", "done", "idle", "waiting_human"})
                stopped = api_hub.stop_24h()
                self.assertTrue(stopped["ok"])


class TestRunHubWaiting(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        _reset_run_hub()

    def test_set_clear_waiting_human(self):
        run_hub.set_waiting_human(reason="hitl_pack", detail={"goal": "x"})
        st = run_hub.status()
        self.assertEqual(st["status"], "waiting_human")
        self.assertEqual(st["waiting_reason"], "hitl_pack")
        run_hub.clear_waiting_human()
        self.assertEqual(run_hub.status()["status"], "idle")


if __name__ == "__main__":
    unittest.main()
