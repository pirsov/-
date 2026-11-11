#!/usr/bin/env python3
"""A29 — installed Ollama tags, no stealth/space-bunny, 404→tags fallback."""
from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from forge import llm, llm_backends, ollama_client
from forge.prompts import AGENT_MODELS, load_model_config


PREFERRED_14B = "qwen2.5-coder:14b-4k"
PREFERRED_7B = "qwen2.5-coder:7b-2k"
INSTALLED = [
    "qwen2.5-coder:7b-2k",
    "qwen2.5-coder:7b",
    "qwen2.5-coder:14b",
    "qwen2.5-coder:14b-2k",
    "qwen2.5-coder:14b-4k",
    "qwen2.5-coder:3b-8k",
    "phi4-mini:4k",
    "roblox-coder:2k",
]


class TestModelsJsonNoStealth(unittest.TestCase):
    def test_models_json_has_no_stealth_space_bunny(self):
        path = Path(__file__).resolve().parents[1] / "forge" / "models.json"
        cfg = json.loads(path.read_text(encoding="utf-8"))
        blob = json.dumps(cfg)
        self.assertNotIn("stealth/space-bunny-alpha", blob)
        self.assertNotIn("stealth/", blob)
        # No model field may use the removed cloud tag
        def _walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in {"model", "escalation"} or isinstance(v, (dict, list)):
                        yield from _walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from _walk(v)
            elif isinstance(obj, str):
                yield obj

        for s in _walk(cfg):
            self.assertNotIn("stealth/space-bunny-alpha", s)
            self.assertFalse(s.startswith("stealth/"), msg=s)
        agents = cfg.get("agents") or {}
        self.assertEqual(agents["gameplay_programmer"]["model"], PREFERRED_14B)
        self.assertEqual(int(agents["gameplay_programmer"].get("num_ctx") or 0), 4096)
        self.assertEqual(agents["client_programmer"]["model"], PREFERRED_14B)
        self.assertEqual(int(agents["client_programmer"].get("num_ctx") or 0), 4096)
        self.assertEqual(agents["refactorer"]["model"], PREFERRED_7B)
        self.assertEqual((cfg.get("repair") or {}).get("model"), PREFERRED_7B)

    def test_loaded_agent_models_match_preferred_tags(self):
        self.assertEqual(AGENT_MODELS["gameplay_programmer"]["model"], PREFERRED_14B)
        self.assertEqual(AGENT_MODELS["client_programmer"]["model"], PREFERRED_14B)
        self.assertEqual(AGENT_MODELS["refactorer"]["model"], PREFERRED_7B)
        cfg = load_model_config()
        self.assertNotIn("stealth/space-bunny-alpha", json.dumps(cfg))


class TestOllama404Fallback(unittest.TestCase):
    def test_404_remaps_to_installed_tag(self):
        # Cloud tag remapped *before* POST using tags list (never hits Ollama as stealth/*)
        with patch.object(ollama_client, "list_models", return_value=list(INSTALLED)):
            with patch("urllib.request.urlopen") as mock_open:
                mock_open.side_effect = lambda req, timeout=0: _FakeResp(
                    {"response": f"OK:{json.loads(req.data.decode()).get('model')}"}
                )
                out = ollama_client.generate(
                    "stealth/space-bunny-alpha",
                    "hi",
                    num_ctx=2048,
                    num_predict=64,
                    timeout=5,
                )
        self.assertIn("OK:", out)
        self.assertIn(PREFERRED_14B, out)

    def test_404_on_missing_local_tag_picks_from_list(self):
        """Preferred local tag missing → one rematch from /api/tags, no 3x same name."""

        models_seen: list[str] = []

        def fake_open(req, timeout=0):
            body = json.loads(req.data.decode("utf-8"))
            models_seen.append(body["model"])
            if body["model"] == "qwen2.5-coder:99b-missing":
                raise urllib.error.HTTPError(
                    "http://localhost:11434/api/generate",
                    404,
                    "Not Found",
                    hdrs=None,
                    fp=io.BytesIO(b'{"error":"model not found"}'),
                )
            return _FakeResp({"response": f"OK:{body['model']}"})

        with patch.object(ollama_client, "list_models", return_value=list(INSTALLED)):
            with patch("urllib.request.urlopen", side_effect=fake_open):
                out = ollama_client.generate(
                    "qwen2.5-coder:99b-missing",
                    "hi",
                    num_ctx=2048,
                    num_predict=64,
                    timeout=5,
                )
        self.assertTrue(out.startswith("OK:"))
        self.assertEqual(models_seen[0], "qwen2.5-coder:99b-missing")
        self.assertEqual(len(models_seen), 2)
        self.assertEqual(models_seen[1], PREFERRED_14B)

    def test_resolve_cloud_tag_to_14b(self):
        got = ollama_client.resolve_model(
            "stealth/space-bunny-alpha", INSTALLED, allow_any=True
        )
        self.assertIsNotNone(got)
        self.assertNotIn("stealth", got or "")
        self.assertIn("coder", (got or "").lower())


class TestPickModelUsesRuntimeOllama(unittest.TestCase):
    def test_openrouter_key_does_not_poison_ollama_pick(self):
        from forge.orchestrator import pick_model

        old = {
            k: os.environ.get(k)
            for k in ("FORGE_BACKEND", "SPACE_BUNNY_API_KEY", "OPENROUTER_API_KEY")
        }
        try:
            os.environ.pop("FORGE_BACKEND", None)
            os.environ.pop("SPACE_BUNNY_API_KEY", None)
            os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-fake"
            llm.reset_runtime_backend()
            # Preferred backend may be openrouter, but runtime is ollama when ping ok
            self.assertEqual(llm.backend_name(), "openrouter")
            with patch.object(llm, "active_backend", return_value="ollama"):
                with patch("forge.orchestrator.installed_models", return_value=list(INSTALLED)):
                    cfg = pick_model("gameplay_programmer", attempt=1, escalate=False)
            self.assertEqual(cfg["model"], PREFERRED_14B)
            self.assertNotIn("stealth", cfg["model"])
            self.assertEqual(int(cfg["ctx"]), 4096)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            llm.reset_runtime_backend()


class TestHardFitKeepsCoinsRemotes(unittest.TestCase):
    def test_drop_order_keeps_coins_remotes_after_rules(self):
        order = llm_backends._DROP_SECTION_ORDER  # noqa: SLF001
        self.assertLess(order.index("RULES"), order.index("COINS TEMPLATE"))
        self.assertLess(order.index("RULES"), order.index("REMOTES TEMPLATE"))
        # Coins/Remotes dropped later than generic QA/Checkpoints templates
        self.assertGreater(order.index("COINS TEMPLATE"), order.index("QA_REPORT TEMPLATE"))
        self.assertGreater(order.index("REMOTES TEMPLATE"), order.index("CHECKPOINTS TEMPLATE"))

    def test_fit_prefers_keeping_coins_over_rules(self):
        fat = (
            "=== RULES ===\n"
            + ("ruleline\n" * 800)
            + "\n=== COINS TEMPLATE ===\n"
            + "Copy this template EXACTLY.\n"
            + ("coinsline\n" * 40)
            + "\n=== YOUR TASK ===\n- [ ] T1 REWRITE Coins\n"
        )
        # Budget tight enough that RULES must go but Coins can stay
        budget = 500
        out, meta = llm_backends.fit_prompt(fat, budget)
        self.assertLessEqual(llm_backends.estimate_tokens(out), budget)
        self.assertIn("COINS TEMPLATE", out)
        self.assertIn("YOUR TASK", out)
        self.assertIn("RULES", meta.get("dropped_sections") or [])


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status = 200

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestLlmOpenrouterDefaultNoStealth(unittest.TestCase):
    def test_explicit_openrouter_no_stealth(self):
        old = {
            k: os.environ.get(k)
            for k in ("FORGE_BACKEND", "SPACE_BUNNY_API_KEY", "OPENROUTER_API_KEY", "OPENROUTER_MODEL")
        }
        try:
            os.environ["FORGE_BACKEND"] = "openrouter"
            os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
            os.environ.pop("OPENROUTER_MODEL", None)
            llm.reset_runtime_backend()
            be, _ = llm.resolve_runtime_backend(ollama_ping_fn=lambda: False, log=False)
            self.assertEqual(be, "openrouter")
            resolved = llm.resolve_model("x")
            self.assertIsNotNone(resolved)
            self.assertNotIn("stealth", resolved or "")
            self.assertNotIn("space-bunny-alpha", resolved or "")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            llm.reset_runtime_backend()


if __name__ == "__main__":
    unittest.main()
