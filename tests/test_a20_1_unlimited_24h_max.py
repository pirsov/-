#!/usr/bin/env python3
"""A20.1: 24h Start must not default to --max 5."""
from __future__ import annotations

import inspect
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import api_hub, run_hub


class TestA201Unlimited24hMax(unittest.TestCase):
    def tearDown(self) -> None:
        run_hub.stop_24h(join_timeout=1.0)
        run_hub._stop_event.clear()
        with run_hub._lock:
            run_hub._state.update(
                {
                    "status": "idle",
                    "mode": None,
                    "loop_cycle": 0,
                    "loop_max": 0,
                    "waiting_reason": None,
                    "waiting_detail": None,
                    "log_path": None,
                    "pid": None,
                }
            )

    def test_default_week_max_steps_is_high(self) -> None:
        self.assertGreaterEqual(run_hub.DEFAULT_WEEK_MAX_STEPS, 500)
        self.assertNotEqual(run_hub.DEFAULT_WEEK_MAX_STEPS, 5)
        sig = inspect.signature(run_hub.start_24h)
        default = sig.parameters["week_max_steps"].default
        self.assertEqual(default, run_hub.DEFAULT_WEEK_MAX_STEPS)

    def test_api_hub_omits_week_max_steps_uses_run_hub_default(self) -> None:
        captured = {}

        def fake_start_24h(root, **kwargs):
            captured.update(kwargs)
            captured["root"] = root
            return {"ok": True, "status": "looping"}

        with patch.object(run_hub, "start_24h", side_effect=fake_start_24h):
            out = api_hub.start_24h(Path("."), sleep=1.0, max_cycles=48)
        self.assertTrue(out.get("ok"))
        # None/omitted → run_hub default applies inside real start_24h; wrapper must not force 5.
        self.assertNotIn("week_max_steps", captured)
        self.assertEqual(captured.get("max_cycles"), 48)

    def test_start_24h_passes_high_max_to_week_burst(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".forge").mkdir(parents=True)
            seen = {}

            def fake_plan_next(_root):
                return {"action": "run_week"}

            def fake_start_week(root, **kwargs):
                seen.update(kwargs)
                with run_hub._lock:
                    run_hub._state["status"] = "done"
                return {"ok": True, "status": "done"}

            with patch("forge.planner.plan_next", side_effect=fake_plan_next), patch.object(
                run_hub, "start_week", side_effect=fake_start_week
            ):
                out = run_hub.start_24h(root, sleep=0.05, max_cycles=1)
                self.assertTrue(out.get("ok"), out)
                # Wait briefly for the loop thread to fire one burst
                deadline = time.time() + 2.0
                while time.time() < deadline and "max_steps" not in seen:
                    time.sleep(0.05)

            self.assertIn("max_steps", seen)
            self.assertEqual(seen["max_steps"], run_hub.DEFAULT_WEEK_MAX_STEPS)
            self.assertGreaterEqual(int(seen["max_steps"]), 500)

    def test_ui_do_start_24h_body_has_no_max_5(self) -> None:
        app = Path(__file__).resolve().parents[1] / "ui" / "app.js"
        text = app.read_text(encoding="utf-8")
        # Locate doStart24h payload — must not hardcode week_max_steps: 5
        self.assertIn("async function doStart24h()", text)
        start = text.index("async function doStart24h()")
        chunk = text[start : start + 500]
        self.assertNotIn("week_max_steps: 5", chunk)
        self.assertNotIn("max: 5", chunk)

    def test_orchestrator_week_default_is_500(self) -> None:
        orch = Path(__file__).resolve().parents[1] / "forge" / "orchestrator.py"
        src = orch.read_text(encoding="utf-8")
        # Spot-check the week branch default assignment (not the old else 200).
        self.assertIn("max_steps = args.max if args.max is not None else 500", src)
        self.assertNotIn("args.max is not None else 200", src)


if __name__ == "__main__":
    unittest.main()
