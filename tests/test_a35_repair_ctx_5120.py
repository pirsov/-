#!/usr/bin/env python3
"""A35.0 — repair 7B ctx=5120; hard cap allows 5120; 14B stays 4096."""
from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import llm_backends, ollama_client
from forge.orchestrator import pick_model
from forge.prompts import AGENT_MODELS, load_model_config


class TestA35RepairCtx5120(unittest.TestCase):
    def test_models_json_repair_5120_gameplay_4096(self):
        cfg = load_model_config()
        repair = cfg.get("repair") or {}
        self.assertEqual(int(repair["ctx"]), 5120)
        self.assertEqual(int(repair.get("num_ctx") or repair["ctx"]), 5120)
        gp = (cfg.get("agents") or {})["gameplay_programmer"]
        self.assertEqual(int(gp["ctx"]), 4096)
        self.assertEqual(int(gp.get("num_ctx") or gp["ctx"]), 4096)
        self.assertEqual(int(AGENT_MODELS["gameplay_programmer"]["ctx"]), 4096)
        self.assertEqual(int(AGENT_MODELS["client_programmer"]["ctx"]), 4096)

    def test_pick_model_repair_explicit_5120_and_log(self):
        buf = io.StringIO()
        with patch("forge.orchestrator.llm.active_backend", return_value="ollama"), patch(
            "forge.orchestrator.llm.backend_name", return_value="ollama"
        ), patch(
            "forge.orchestrator.installed_models",
            return_value=["qwen2.5-coder:7b-2k", "qwen2.5-coder:14b-4k"],
        ), patch(
            "forge.orchestrator.llm.resolve_model", side_effect=lambda p, *a, **k: p
        ), patch("sys.stdout", buf):
            cfg = pick_model("gameplay_programmer", attempt=2, escalate=True)
        self.assertEqual(int(cfg["ctx"]), 5120)
        self.assertEqual(int(cfg.get("num_ctx") or cfg["ctx"]), 5120)
        self.assertTrue(cfg.get("is_7b"))
        self.assertIn("[7B] num_ctx=5120 predict=", buf.getvalue())

    def test_pick_model_14b_stays_4096(self):
        with patch("forge.orchestrator.llm.active_backend", return_value="ollama"), patch(
            "forge.orchestrator.llm.backend_name", return_value="ollama"
        ), patch(
            "forge.orchestrator.installed_models",
            return_value=["qwen2.5-coder:7b-2k", "qwen2.5-coder:14b-4k"],
        ), patch(
            "forge.orchestrator.llm.resolve_model", side_effect=lambda p, *a, **k: p
        ):
            cfg = pick_model("gameplay_programmer", attempt=1, escalate=False)
        self.assertEqual(int(cfg["ctx"]), 4096)
        self.assertEqual(int(cfg.get("num_ctx") or cfg["ctx"]), 4096)
        self.assertFalse(cfg.get("is_7b"))

    def test_cap_allows_5120(self):
        self.assertGreaterEqual(llm_backends.MAX_NUM_CTX, 5120)
        self.assertEqual(llm_backends.MAX_NUM_CTX, 8192)
        self.assertEqual(llm_backends.cap_num_ctx(5120), 5120)
        opts = llm_backends.ollama_options(num_ctx=5120, num_predict=512, diff_mode=True)
        self.assertEqual(opts["num_ctx"], 5120)

    def test_ollama_generate_fallback_cap_8192(self):
        """Exception path in generate must not clamp 5120 down to 4096."""
        src = Path(ollama_client.__file__).read_text(encoding="utf-8")
        self.assertIn("min(int(num_ctx), 8192)", src)
        self.assertNotIn("min(int(num_ctx), 4096)", src)


if __name__ == "__main__":
    unittest.main()
