#!/usr/bin/env python3
"""A36.0 — Fix generation cutoff: 14B predict=2048; DONE-without-FILE auto-wrap."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from forge import llm_backends
from forge.orchestrator import parse_agent_output, pick_model
from forge.prompts import AGENT_MODELS, load_model_config


class TestA36Predict2048(unittest.TestCase):
    def test_models_json_14b_predict_2048_repair_ctx_5120(self):
        cfg = load_model_config()
        agents = cfg.get("agents") or {}
        for role in ("gameplay_programmer", "client_programmer"):
            self.assertEqual(int(agents[role]["predict"]), 2048, msg=role)
            self.assertEqual(int(AGENT_MODELS[role]["predict"]), 2048, msg=role)
            self.assertEqual(int(agents[role]["ctx"]), 4096, msg=role)
        repair = cfg.get("repair") or {}
        self.assertEqual(int(repair["ctx"]), 5120)
        self.assertEqual(int(repair.get("num_ctx") or repair["ctx"]), 5120)
        week = cfg.get("week_mode") or {}
        self.assertEqual(int(week.get("max_predict_code") or 0), 2048)
        ollama = cfg.get("ollama") or {}
        self.assertEqual(int(ollama.get("num_predict") or 0), 2048)

    def test_pick_model_14b_predict_2048(self):
        with patch("forge.orchestrator.llm.active_backend", return_value="ollama"), patch(
            "forge.orchestrator.llm.backend_name", return_value="ollama"
        ), patch(
            "forge.orchestrator.installed_models",
            return_value=["qwen2.5-coder:7b-2k", "qwen2.5-coder:14b-4k"],
        ), patch(
            "forge.orchestrator.llm.resolve_model", side_effect=lambda p, *a, **k: p
        ):
            for role in ("gameplay_programmer", "client_programmer"):
                cfg = pick_model(role, attempt=1, escalate=False)
                self.assertEqual(int(cfg["predict"]), 2048, msg=role)
                self.assertEqual(int(cfg["ctx"]), 4096, msg=role)
                self.assertFalse(cfg.get("is_7b"), msg=role)

    def test_cap_allows_2048(self):
        self.assertGreaterEqual(llm_backends.CODE_NUM_PREDICT_MAX, 2048)
        self.assertEqual(llm_backends.cap_num_predict(2048), 2048)
        self.assertEqual(llm_backends.cap_num_predict(9999), 2048)
        opts = llm_backends.ollama_options(num_ctx=4096, num_predict=2048)
        self.assertEqual(opts["num_predict"], 2048)


class TestA36AutoWrapDoneWithoutFile(unittest.TestCase):
    def test_auto_wrap_long_body_uses_target_path(self):
        body = "local x = 1\n" + ("print(x)\n" * 80)  # >500 chars
        self.assertGreater(len(body), 500)
        out = f"<DONE>T360</DONE>\n<NOTE>ok</NOTE>\n{body}"
        done, note, files, blocked = parse_agent_output(
            out, "T360", target_path="src/server/Gameplay/Checkpoints.server.luau"
        )
        self.assertEqual(done, "T360")
        self.assertEqual(note, "ok")
        self.assertIsNone(blocked)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, "src/server/Gameplay/Checkpoints.server.luau")
        self.assertIn("local x = 1", files[0].content)
        self.assertGreater(len(files[0].content), 500)

    def test_short_body_no_wrap(self):
        out = "<DONE>T1</DONE>\n<NOTE>tiny</NOTE>\nprint(1)\n"
        done, note, files, _ = parse_agent_output(
            out, "T1", target_path="src/server/X.luau"
        )
        self.assertEqual(done, "T1")
        self.assertEqual(files, [])

    def test_unclosed_file_recovered(self):
        body = "--!strict\n" + ("local n = 1\n" * 60)
        self.assertGreater(len(body), 500)
        out = (
            f"<DONE>P1</DONE>\n<NOTE>cut</NOTE>\n"
            f'<FILE path="src/server/Gameplay/Puzzles.server.luau">\n{body}'
        )
        done, note, files, _ = parse_agent_output(
            out, "P1", target_path="src/server/Gameplay/Puzzles.server.luau"
        )
        self.assertEqual(done, "P1")
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, "src/server/Gameplay/Puzzles.server.luau")
        self.assertIn("--!strict", files[0].content)

    def test_closed_file_unchanged(self):
        out = (
            "<DONE>A1</DONE>\n<NOTE>hi</NOTE>\n"
            '<FILE path="src/x.luau">\n--!strict\nprint(1)\n</FILE>\n'
        )
        done, note, files, _ = parse_agent_output(out, "A1", target_path="src/x.luau")
        self.assertEqual(done, "A1")
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].content.strip(), "--!strict\nprint(1)")


if __name__ == "__main__":
    unittest.main()
