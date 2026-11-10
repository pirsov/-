#!/usr/bin/env python3
"""A13.0 Token Economy — EN cards, minify, short keys, bundle savings."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestTokenEconomyHelpers(unittest.TestCase):
    def test_englishize_and_short_keys(self):
        from forge import token_economy as te

        ru = "Не используй DataStore на клиенте — запрещено"
        en = te.englishize_text(ru)
        self.assertFalse(te.has_cyrillic(en))
        self.assertIn("do not use", en.lower())
        card = {
            "id": "demo",
            "purpose": "сервер сохранение монет",
            "exports": ["save_coins()"],
            "forbid": ["запрещено wait()"],
            "attrs": ["Coins"],
        }
        lean = te.economy_card(card)
        self.assertIn("exp", lean)
        self.assertIn("f", lean)
        self.assertIn("p", lean)
        self.assertNotIn("exports", lean)
        self.assertFalse(te.has_cyrillic(lean["p"]))

    def test_dumps_disk_minified(self):
        from forge import token_economy as te

        raw = te.dumps_disk({"a": 1, "b": [2, 3]})
        self.assertNotIn("\n  ", raw)
        self.assertIn('{"a":1', raw.replace(" ", ""))
        old = os.environ.get("FORGE_JSON_PRETTY")
        try:
            os.environ["FORGE_JSON_PRETTY"] = "1"
            pretty = te.dumps_disk({"a": 1})
            self.assertIn("\n", pretty)
        finally:
            if old is None:
                os.environ.pop("FORGE_JSON_PRETTY", None)
            else:
                os.environ["FORGE_JSON_PRETTY"] = old


class TestBundleSavings(unittest.TestCase):
    def test_economy_bundle_smaller_percent(self):
        from forge import skills_hub

        # Realistic fixture: RU purpose + fat forbid lines + skeleton + rules
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            card_dir = root / "skills" / "compact" / "forge-demo"
            card_dir.mkdir(parents=True)
            card = {
                "id": "forge-demo",
                "purpose": "Клиентский UI для монет — обязательно показывать Score на сервере нельзя",
                "exports": [
                    "GetAttribute(\"Coins\") — читать с Player",
                    "SetAttribute(\"Coins\", n) — только сервер",
                    "FireServer(\"Donate\")",
                ],
                "attrs": ["Coins", "Score", "BestTime", "Checkpoint"],
                "forbid": [
                    "НЕ используй DataStoreService на клиенте — запрещено",
                    "Никогда не вызывай wait() — только task.wait()",
                    "Запрещено character:GetAttribute(\"Coins\")",
                ],
                "files": ["src/client/CoinHUD.client.luau"],
            }
            (card_dir / "CARD.json").write_text(
                json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            # KB with RU active rule
            kb = {
                "version": 1,
                "rules": [
                    {
                        "id": "R001",
                        "status": "active",
                        "human_comment": "Не используй DataStore на клиенте",
                        "checks": [{"type": "forbid_substr", "text": "DataStoreService"}],
                    }
                ],
                "plugins": {},
            }
            (root / "knowledge_base.json").write_text(
                json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            # minimal skeleton registry so inject works if present
            skel = root / "skeletons" / "client_ui" / "v1"
            skel.mkdir(parents=True)
            (skel / "META.json").write_text(
                json.dumps({"id": "client_ui", "version": "v1", "forbid": ["DataStoreService"]}),
                encoding="utf-8",
            )
            (skel / "SKELETON.luau").write_text(
                "--!strict\n"
                "-- verbose decorative comment block that economy mode should keep short via budget\n"
                "local Players = game:GetService(\"Players\")\n"
                "local gui = Instance.new(\"ScreenGui\")\n",
                encoding="utf-8",
            )
            (root / "skeletons" / "registry.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "archetypes": {
                            "client_ui": {
                                "latest": "v1",
                                "versions": ["v1"],
                                "summary": "LocalScript UI",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = skills_hub.bundle_savings_report(
                root,
                ["forge-demo"],
                archetype="client_ui",
                skeleton_version="v1",
                skeleton_budget=400,
            )
            self.assertGreater(report["bytes_before"], report["bytes_after"])
            self.assertGreaterEqual(report["percent_saved"], 15.0)
            lean = skills_hub.bundle_for_14b(
                root, ["forge-demo"], economy=True, archetype="client_ui", skeleton_version="v1"
            )
            fat = skills_hub.bundle_for_14b(
                root, ["forge-demo"], economy=False, archetype="client_ui", skeleton_version="v1"
            )
            self.assertIn('"exp"', lean)
            self.assertIn("exports", fat)
            self.assertIn("===CARDS===", lean)
            self.assertIn("CONTRACT CARDS", fat)
            # write artifact for human report
            art = ROOT / "artifacts" / "a13_token_economy"
            art.mkdir(parents=True, exist_ok=True)
            # also measure against live repo cards
            live = skills_hub.bundle_savings_report(
                ROOT,
                ["forge-player-attrs", "forge-luau-touch", "forge-ui-modern"],
                archetype="client_ui",
                skeleton_version="v1",
                skeleton_budget=500,
            )
            payload = {
                "fixture": report,
                "live_repo": live,
                "note": "A13.0 Token Economy — percent_saved is bytes shrink of bundle_for_14b",
            }
            (art / "bundle_savings.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (art / "REPORT.md").write_text(
                "# A13.0 Token Economy — bundle savings\n\n"
                f"- Fixture (RU card + rules): **{report['percent_saved']}%** "
                f"({report['bytes_before']} → {report['bytes_after']} bytes)\n"
                f"- Live repo cards: **{live['percent_saved']}%** "
                f"({live['bytes_before']} → {live['bytes_after']} bytes)\n\n"
                "Levers: EN purpose/forbid, short keys (exp/f/p), minified JSON, "
                "compact RULES header, CODE_ECONOMY prompt rules, EN summaries on compact.\n",
                encoding="utf-8",
            )


class TestStateMinifyAndEnglishSummary(unittest.TestCase):
    def test_compact_englishizes_summary_and_minifies(self):
        from forge.state_hub import compact_state, load_state, save_state

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = {
                "pulse": {"cycle": 5},
                "done": [
                    {
                        "plugin": "system.coins",
                        "status": "done",
                        "closed_cycle": 1,
                        "contract_snapshot": {
                            "name": "system.coins",
                            "purpose": "Сохранение монет на сервере — обязательно pcall",
                            "exports": ["save_coins()"],
                        },
                    }
                ],
                "task_queue": [],
            }
            save_state(root, state)
            raw = (root / "state.json").read_text(encoding="utf-8")
            self.assertNotIn("\n  ", raw)  # minified
            report = compact_state(root, force=True, keep_recent_cycles=0)
            self.assertEqual(report["compacted"], 1)
            entry = load_state(root)["done"][0]
            summary = entry.get("contract_summary") or ""
            self.assertFalse(any("\u0400" <= c <= "\u04FF" for c in summary))
            cref = root / entry["contract_ref"]
            self.assertTrue(cref.is_file())
            craw = cref.read_text(encoding="utf-8")
            self.assertNotIn("\n  ", craw)
            payload = json.loads(craw)
            self.assertIn("contract_snapshot", payload)


class TestPromptEconomyRule(unittest.TestCase):
    def test_strict_rules_mention_token_economy(self):
        text = (ROOT / "forge" / "prompts.py").read_text(encoding="utf-8")
        self.assertIn("TOKEN ECONOMY", text)
        self.assertIn("Do not write excessive comments", text)


if __name__ == "__main__":
    unittest.main()
