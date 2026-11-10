#!/usr/bin/env python3
"""waiting_human must not burn 24h max_cycles."""
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import run_hub


class TestWaitingHumanCycles(unittest.TestCase):
    def tearDown(self) -> None:
        run_hub.stop_24h(join_timeout=2.0)
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
                }
            )

    def test_waiting_human_does_not_consume_cycles(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".forge").mkdir(parents=True)

            calls = {"n": 0}

            def fake_plan_next(_root):
                calls["n"] += 1
                return {
                    "action": "verify_plugin",
                    "plugin": "game1.hud",
                    "hint": "feedback",
                }

            # Keep park short for the test; cycle must stay 0 while waiting
            with patch("forge.planner.plan_next", side_effect=fake_plan_next):
                out = run_hub.start_24h(root, sleep=0.2, max_cycles=48, week_max_steps=1)
                self.assertTrue(out.get("ok"), out)

                # Wait until waiting_human is set
                deadline = time.time() + 3.0
                while time.time() < deadline:
                    st = run_hub.status()
                    if st.get("status") == "waiting_human":
                        break
                    time.sleep(0.05)
                st = run_hub.status()
                self.assertEqual(st.get("status"), "waiting_human", st)
                self.assertEqual(int(st.get("loop_cycle") or 0), 0, st)

                # Remain waiting for > one park slice; cycle must not climb toward 48
                time.sleep(0.8)
                st2 = run_hub.status()
                self.assertEqual(st2.get("status"), "waiting_human", st2)
                self.assertEqual(int(st2.get("loop_cycle") or 0), 0, st2)
                self.assertLess(calls["n"], 10, "must not spin plan_next every ms")

                # Human answers → clear waiting; still should not have burned budget
                run_hub.clear_waiting_human()
                time.sleep(0.15)
                st3 = run_hub.status()
                self.assertLessEqual(int(st3.get("loop_cycle") or 0), 1, st3)

                run_hub.stop_24h(join_timeout=2.0)

    def test_status_not_overwritten_to_looping_while_waiting(self):
        run_hub.set_waiting_human(reason="verify_plugin", detail={"plugin": "game1.hud"})
        with run_hub._lock:
            run_hub._state["mode"] = "loop_24h"
        # Simulate the old bug: blindly writing looping must not happen via public API
        st = run_hub.status()
        self.assertEqual(st.get("status"), "waiting_human")


if __name__ == "__main__":
    unittest.main()
