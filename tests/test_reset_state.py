#!/usr/bin/env python3
"""Tests for --reset-state and DeepSeek missing-key TZ behavior."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import deepseek, llm, progress_hub, run_hub, state_hub
from forge.orchestrator import main


def _seed_stuck_root(root: Path) -> None:
    (root / "projects" / "game1" / "src").mkdir(parents=True)
    (root / "projects" / "game1" / "smoke").mkdir(parents=True)
    (root / "src").mkdir(parents=True)
    (root / ".forge").mkdir(parents=True)
    (root / "projects" / "game1" / "meta.json").write_text(
        json.dumps({"id": "game1", "status": "stuck", "smoke": {"pending": False}}),
        encoding="utf-8",
    )
    (root / "projects" / "game1" / "PROJECT_TZ.md").write_text(
        "# old game1\n## AGENT\n- [x] T1 | done | @gameplay_programmer | -> src/a.luau\n",
        encoding="utf-8",
    )
    (root / "PROJECT_TZ.md").write_text(
        "# live old\n## AGENT\n- [ ] T1 | leftover | @gameplay_programmer | -> src/a.luau\n"
        "- [ ] T2 | leftover | @gameplay_programmer | -> src/b.luau\n"
        "- [ ] T3 | leftover | @gameplay_programmer | -> src/c.luau\n"
        "- [ ] T4 | leftover | @gameplay_programmer | -> src/d.luau\n"
        "- [ ] T5 | leftover | @gameplay_programmer | -> src/e.luau\n",
        encoding="utf-8",
    )
    (root / "projects" / "game1" / "smoke" / "latest.json").write_text(
        json.dumps({"overall_ok": True, "answers": {}}), encoding="utf-8"
    )
    (root / "state.json").write_text(
        json.dumps(
            {
                "milestone": "keep-me",
                "pulse": {"cycle": 48, "status": "smoke"},
                "done": [
                    {"plugin": "forge.validator", "status": "done"},
                    {"plugin": "game2.hud", "status": "closed_verified"},
                    {"plugin": "game1.coins", "status": "done"},
                ],
                "task_queue": [
                    {"id": "T9", "status": "in_progress"},
                    {"id": "H1", "status": "ready"},
                ],
                "partial": [{"id": "x"}],
                "open_questions": [{"id": "Q1"}],
                "pending_hitl_pack": {"questions": [{"id": "Q1"}]},
                "last_chat": {"message": "old"},
            }
        ),
        encoding="utf-8",
    )
    progress_hub.save(
        root,
        {
            "activated": True,
            "skills_done": True,
            "tz_done": True,
            "run_done": True,
            "smoke_done": True,
            "fix_tz_done": True,
            "fix_done": True,
            "skipped": [],
        },
    )
    with run_hub._lock:
        run_hub._state.update(
            {
                "status": "done",
                "mode": None,
                "loop_cycle": 48,
                "loop_max": 48,
                "waiting_reason": None,
            }
        )


class TestResetState(unittest.TestCase):
    def tearDown(self) -> None:
        run_hub._stop_event.clear()
        with run_hub._lock:
            run_hub._state.update(
                {
                    "status": "idle",
                    "loop_cycle": 0,
                    "loop_max": 0,
                    "mode": None,
                    "waiting_reason": None,
                    "waiting_detail": None,
                }
            )

    def test_reset_state_project_scopes_and_clears_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_stuck_root(root)
            # unrelated project must survive
            other = root / "projects" / "game1" / "PROJECT_TZ.md"
            other_text = other.read_text(encoding="utf-8")

            report = state_hub.reset_state(root, project_id="game2")
            self.assertTrue(report["ok"])
            self.assertEqual(report["project"], "game2")
            self.assertEqual(report["pulse_cycle"], 0)
            self.assertEqual(report["queue_len"], 0)
            self.assertEqual(report["loop_cycle"], 0)
            self.assertEqual(report["loop_max"], 0)

            st = state_hub.load_state(root)
            self.assertEqual(st["pulse"]["cycle"], 0)
            self.assertEqual(st["task_queue"], [])
            self.assertEqual(st.get("open_questions"), [])
            self.assertNotIn("pending_hitl_pack", st)
            self.assertEqual(st.get("milestone"), "keep-me")
            plugins = {d.get("plugin") for d in st.get("done") or []}
            self.assertIn("forge.validator", plugins)
            self.assertIn("game1.coins", plugins)
            self.assertNotIn("game2.hud", plugins)

            tz = (root / "projects" / "game2" / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("fresh start", tz)
            self.assertNotIn("- [ ] T1", tz)
            live = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("game2", live)
            self.assertEqual(other.read_text(encoding="utf-8"), other_text)

            active = json.loads((root / ".forge" / "active_project.json").read_text(encoding="utf-8"))
            self.assertEqual(active["id"], "game2")
            prog = progress_hub.load(root)
            self.assertFalse(prog.get("smoke_done"))
            self.assertFalse(prog.get("run_done"))
            self.assertEqual(run_hub.status().get("loop_cycle"), 0)

    def test_cli_reset_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_stuck_root(root)
            code = main(["--root", str(root), "--reset-state", "--project", "game2"])
            self.assertEqual(code, 0)
            st = state_hub.load_state(root)
            self.assertEqual(st["task_queue"], [])
            self.assertEqual(st["pulse"]["cycle"], 0)
            self.assertTrue((root / "projects" / "game2" / "meta.json").is_file())

    def test_bare_reset_clears_verify_plugin_leftovers(self):
        """python -u run.py --reset-state must wipe game done[] that re-triggers verify."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_stuck_root(root)
            report = state_hub.reset_state(root, project_id=None)
            self.assertTrue(report["ok"])
            self.assertTrue(report.get("cleared_verify"))
            st = state_hub.load_state(root)
            self.assertEqual(st["task_queue"], [])
            self.assertEqual(st.get("partial"), [])
            self.assertNotIn("pending_hitl_pack", st)
            plugins = {d.get("plugin") for d in st.get("done") or []}
            self.assertIn("forge.validator", plugins)
            self.assertNotIn("game1.coins", plugins)
            self.assertNotIn("game2.hud", plugins)
            # planner must not immediately ask verify_plugin on leftover game1.coins
            from forge import planner

            with patch("forge.deepseek.ask_hitl_pack", return_value={"questions": []}):
                plan = planner.plan_next(root)
            self.assertNotEqual(plan.get("action"), "verify_plugin", plan)


class TestDeepSeekMissingKey(unittest.TestCase):
    def test_generate_project_tz_raises_without_key(self):
        env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(deepseek.available())
            with self.assertRaises(llm.AuthError) as ctx:
                deepseek.generate_project_tz(
                    project_id="game2",
                    goal="new apple sim",
                    compact_skills=["forge-player-attrs"],
                    existing_files=[],
                )
            msg = str(ctx.exception)
            self.assertIn("DEEPSEEK_API_KEY", msg)
            self.assertIn("stale", msg.lower())

    def test_missing_key_does_not_return_horror_fallback(self):
        env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(llm.AuthError):
                out = deepseek.generate_project_tz(
                    project_id="game2",
                    goal="anything",
                    compact_skills=[],
                    existing_files=[],
                )
                # must not reach — guard against silent fallback regression
                self.assertNotIn("horror coins", out.lower())


if __name__ == "__main__":
    unittest.main()
