#!/usr/bin/env python3
"""A15.0 Advanced Context Optimization — predict caps, patches, prune, 7B compact."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestNumPredictCaps(unittest.TestCase):
    def test_cap_default_and_diff(self):
        from forge import llm_backends

        # A36: code predict ceiling raised to 2048 (was 1024) so FILE tags can close
        self.assertLessEqual(llm_backends.DEFAULT_NUM_PREDICT, 2048)
        self.assertLessEqual(llm_backends.DIFF_NUM_PREDICT, 512)
        self.assertEqual(
            llm_backends.cap_num_predict(9999),
            max(llm_backends.DEFAULT_NUM_PREDICT, llm_backends.CODE_NUM_PREDICT_MAX),
        )
        self.assertEqual(
            llm_backends.cap_num_predict(9999, diff_mode=True), llm_backends.DIFF_NUM_PREDICT
        )


class TestPatchApply(unittest.TestCase):
    def test_search_replace(self):
        from forge import patch_apply

        existing = "local a = 1\nlocal b = 2\nlocal c = 3\n"
        body = (
            "<<<<<<< SEARCH\n"
            "local b = 2\n"
            "=======\n"
            "local b = 99\n"
            ">>>>>>> REPLACE\n"
        )
        out, how = patch_apply.materialize_file_content(existing, body)
        self.assertEqual(how, "patch")
        self.assertIn("local b = 99", out)
        self.assertIn("local a = 1", out)

    def test_full_when_no_patch(self):
        from forge import patch_apply

        out, how = patch_apply.materialize_file_content("old", "new full content")
        self.assertEqual(how, "full")
        self.assertEqual(out, "new full content")


class TestSemanticPrune(unittest.TestCase):
    def test_prune_keeps_matching_exports(self):
        from forge import token_economy as te

        card = {
            "id": "demo",
            "exports": [
                "get_player_coins(player)",
                "save_player(player)",
                "unrelated_widget()",
            ],
            "forbid": ["DataStoreService on client", "wait()"],
            "attrs": ["Coins", "Score", "BestTime"],
        }
        pruned = te.prune_card(card, ["get_player_coins", "Coins"])
        self.assertEqual(len(pruned["exports"]), 1)
        self.assertIn("get_player_coins", pruned["exports"][0])
        self.assertTrue(any("Coins" in a for a in pruned["attrs"]))

    def test_bundle_prune_saves_bytes(self):
        from forge import skills_hub

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = root / "skills" / "compact" / "forge-demo"
            d.mkdir(parents=True)
            card = {
                "id": "forge-demo",
                "exports": [
                    "get_player_coins()",
                    "set_player_coins()",
                    "save_inventory()",
                    "load_inventory()",
                    "reset_season()",
                ],
                "attrs": ["Coins", "Gems", "XP", "Level", "Badge"],
                "forbid": ["DataStore on client", "while true", "wait()", "FireServer spoof"],
                "files": [],
            }
            (d / "CARD.json").write_text(json.dumps(card), encoding="utf-8")
            fat = skills_hub.bundle_for_14b(
                root, ["forge-demo"], economy=False, prune=False
            )
            lean = skills_hub.bundle_for_14b(
                root,
                ["forge-demo"],
                economy=True,
                prune=True,
                focus_terms=["get_player_coins", "Coins"],
            )
            self.assertLess(len(lean), len(fat))
            self.assertIn("get_player_coins", lean)
            # pruned away unrelated
            self.assertNotIn("reset_season", lean)


class TestPromptDiffMode(unittest.TestCase):
    def test_rewrite_existing_asks_complete_file_not_patch(self):
        # A28: Cursor SEARCH/REPLACE markers break files — COMPLETE only.
        from forge.prompts import mode_instructions
        from forge.task_parser import Task, WriteMode

        task = Task(
            task_id="T1",
            description="fix coins",
            owner="gameplay_programmer",
            target_path="src/server/X.luau",
            mode=WriteMode.REWRITE,
            raw="- [ ] T1 | REWRITE",
            requires_file=True,
            section=None,
        )
        text = mode_instructions(task, file_exists=True, prefer_diff=True)
        self.assertIn("COMPLETE", text)
        self.assertIn("NEVER use <<<<<<< SEARCH", text)
        self.assertNotIn("Prefer SEARCH/REPLACE blocks", text)


class TestCompact7bFallback(unittest.TestCase):
    def test_summarize_falls_back_without_ollama(self):
        from forge import llm_backends

        old = os.environ.get("FORGE_COMPACT_7B")
        try:
            os.environ["FORGE_COMPACT_7B"] = "0"
            out = llm_backends.summarize_local(
                "Сохранение монет на сервере — обязательно pcall", max_chars=80
            )
            self.assertFalse(any("\u0400" <= c <= "\u04FF" for c in out))
        finally:
            if old is None:
                os.environ.pop("FORGE_COMPACT_7B", None)
            else:
                os.environ["FORGE_COMPACT_7B"] = old


if __name__ == "__main__":
    unittest.main()
