#!/usr/bin/env python3
"""Regression: HITL answer must unblock 24h → --week (no infinite ask_hitl / Lock deadlock)."""
from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import api_hub, planner, run_hub


SAMPLE_PACK = {
    "kind": "hitl_pack",
    "cycle": 1,
    "questions": [
        {
            "id": "Q1",
            "topic": "fruits",
            "ask": "Какой фрукт первый?",
            "options": [
                {"key": "A", "label": "Apple"},
                {"key": "B", "label": "Banana"},
                {"key": "C", "label": "Watermelon"},
            ],
            "other": {"key": "other", "label": "Другое", "allows_text": True},
            "default_if_timeout": "A",
        }
    ],
}


def _reset_run_hub() -> None:
    run_hub.stop_24h(join_timeout=1.0)
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


def _write_state(root: Path, payload: dict) -> None:
    (root / "state.json").write_text(json.dumps(payload), encoding="utf-8")
    (root / "knowledge_base.json").write_text(
        json.dumps({"rules": [], "plugins": {}}), encoding="utf-8"
    )


class TestPlanNextUnblock(unittest.TestCase):
    def test_after_hitl_returns_idle_not_new_pack(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_state(
                root,
                {
                    "pulse": {"cycle": 2},
                    "done": [],
                    "task_queue": [{"id": "T1", "status": "ready", "title": "Apple"}],
                    "open_questions": [
                        {
                            "id": "Q1",
                            "status": "answered",
                            "answer": {"key": "A", "label": "Apple"},
                        }
                    ],
                },
            )
            with patch("forge.deepseek.ask_hitl_pack") as mocked:
                out = planner.plan_next(root, focus="after_hitl")
            mocked.assert_not_called()
            self.assertEqual(out["action"], "idle", out)
            self.assertEqual(out.get("reason"), "ready_for_week")

    def test_answered_without_focus_skips_reask(self):
        """24h loop calls plan_next(root) with empty focus after clear_waiting_human."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_state(
                root,
                {
                    "pulse": {"cycle": 2},
                    "done": [],
                    "task_queue": [],
                    "open_questions": [
                        {"id": "Q1", "status": "answered", "answer": {"key": "B"}}
                    ],
                },
            )
            with patch("forge.deepseek.ask_hitl_pack") as mocked:
                out = planner.plan_next(root)
            mocked.assert_not_called()
            self.assertEqual(out["action"], "idle", out)

    def test_game1_leftover_does_not_block_after_hitl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_state(
                root,
                {
                    "pulse": {"cycle": 1},
                    "done": [{"plugin": "game1.remotes", "status": "done"}],
                    "task_queue": [{"id": "T1", "status": "ready"}],
                    "open_questions": [
                        {"id": "Q1", "status": "answered", "answer": {"key": "A"}}
                    ],
                },
            )
            out = planner.plan_next(root, focus="after_hitl")
            self.assertEqual(out["action"], "idle", out)
            self.assertNotEqual(out.get("action"), "verify_plugin")

    def test_pending_pack_resumed_not_regenerated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_state(
                root,
                {
                    "pulse": {"cycle": 1},
                    "done": [],
                    "task_queue": [],
                    "open_questions": [],
                    "pending_hitl_pack": SAMPLE_PACK,
                },
            )
            with patch("forge.deepseek.ask_hitl_pack") as mocked:
                out = planner.plan_next(root)
            mocked.assert_not_called()
            self.assertEqual(out["action"], "ask_hitl")
            self.assertTrue(out.get("resumed"))
            self.assertEqual(out["pack"]["questions"][0]["id"], "Q1")

    def test_fresh_state_still_asks_hitl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_state(
                root,
                {"pulse": {"cycle": 0}, "done": [], "task_queue": [], "open_questions": []},
            )
            with patch("forge.deepseek.ask_hitl_pack", return_value=SAMPLE_PACK):
                out = planner.plan_next(root, focus="fruits")
            self.assertEqual(out["action"], "ask_hitl")


class TestRunHubNoDeadlock(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        _reset_run_hub()

    def test_start_week_while_looping_returns_without_deadlock(self):
        with run_hub._lock:
            run_hub._state.update({"status": "looping", "mode": "loop_24h"})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            done = {"ok": False}

            def call() -> None:
                out = run_hub.start_week(root, sleep=0, hitl="y", max_steps=1)
                done["out"] = out
                done["ok"] = True

            t = threading.Thread(target=call, daemon=True)
            t.start()
            t.join(timeout=2.0)
            self.assertFalse(t.is_alive(), "start_week deadlocked on Lock+status()")
            self.assertTrue(done["ok"])
            self.assertFalse(done["out"].get("ok"))
            self.assertIn("already running", str(done["out"].get("error") or ""))

    def test_start_week_allow_from_loop_spawns(self):
        with run_hub._lock:
            run_hub._state.update({"status": "looping", "mode": "loop_24h"})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "run.py").write_text("print('week-ok')\n", encoding="utf-8")

            class FakeProc:
                def __init__(self) -> None:
                    self.pid = 4242
                    self.stdout = iter(["week-ok\n"])

                def wait(self) -> int:
                    return 0

            with patch("forge.run_hub.subprocess.Popen", return_value=FakeProc()):
                out = run_hub.start_week(
                    root, sleep=0, hitl="y", max_steps=1, allow_from_loop=True
                )
            self.assertTrue(out.get("ok"), out)
            # worker may finish quickly → looping or running/done
            deadline = time.time() + 2.0
            while time.time() < deadline:
                st = run_hub.status().get("status")
                if st in {"running", "looping", "done"}:
                    break
                time.sleep(0.05)
            self.assertIn(run_hub.status().get("status"), {"running", "looping", "done"})


class TestAnswerClearsAndIdles(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        _reset_run_hub()

    def test_answer_then_plan_idle_snapshot_no_pack(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_state(
                root,
                {
                    "pulse": {"cycle": 1},
                    "done": [{"plugin": "game1.coins", "status": "done"}],
                    "task_queue": [{"id": "T1", "status": "ready"}],
                    "open_questions": [],
                    "pending_hitl_pack": SAMPLE_PACK,
                },
            )
            run_hub.set_waiting_human(reason="hitl_pack")
            with run_hub._lock:
                run_hub._state["mode"] = "loop_24h"

            out = api_hub.answer(root, answer_str="Q1=A")
            self.assertTrue(out.get("ok"), out)
            self.assertEqual(out.get("status"), "answered")
            self.assertEqual(out.get("next", {}).get("action"), "idle", out)
            snap = out.get("snapshot") or {}
            self.assertFalse(snap.get("waiting_human"))
            self.assertFalse(snap.get("pending_hitl"))
            self.assertIsNone(snap.get("hitl_pack"))
            # 24h mode resumes to looping after clear
            self.assertEqual(run_hub.status().get("status"), "looping")


class TestTwentyFourHReachesWeek(unittest.TestCase):
    def setUp(self) -> None:
        _reset_run_hub()

    def tearDown(self) -> None:
        _reset_run_hub()

    def test_after_clear_loop_calls_start_week(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".forge").mkdir(parents=True)
            _write_state(
                root,
                {
                    "pulse": {"cycle": 1},
                    "done": [],
                    "task_queue": [{"id": "T1", "status": "ready"}],
                    "open_questions": [
                        {"id": "Q1", "status": "answered", "answer": {"key": "A"}}
                    ],
                },
            )
            calls = {"week": 0}

            def fake_week(*_a, **kwargs):
                calls["week"] += 1
                self.assertTrue(kwargs.get("allow_from_loop"), kwargs)
                with run_hub._lock:
                    run_hub._state["status"] = "done"
                return {"ok": True, "status": "done", "pid": None}

            with patch("forge.planner.plan_next", return_value={"action": "idle", "cycle": 1}), patch(
                "forge.run_hub.start_week", side_effect=fake_week
            ):
                out = run_hub.start_24h(root, sleep=0.2, max_cycles=2, week_max_steps=1)
                self.assertTrue(out.get("ok"), out)
                deadline = time.time() + 3.0
                while time.time() < deadline and calls["week"] < 1:
                    time.sleep(0.05)
                run_hub.stop_24h(join_timeout=3.0)
            self.assertGreaterEqual(calls["week"], 1, "24h must invoke start_week after idle plan")


if __name__ == "__main__":
    unittest.main()
