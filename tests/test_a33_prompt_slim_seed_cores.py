#!/usr/bin/env python3
"""A33 — Prompt slim (~1500), repair stub accept, skip-after-3-fails, seeded Remotes."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge import llm_backends, state_hub
from forge.orchestrator import (
    Orchestrator,
    enqueue_missing_expected_rewrites,
    maybe_skip_after_target_fails,
    repair_stub_structure_ok,
)
from forge.prompts import build_prompt, load_model_config
from forge.task_parser import Task, WriteMode
from forge.validator import validate_file

ROOT = Path(__file__).resolve().parent.parent
REMOTES = ROOT / "src/shared/Gameplay/Remotes.luau"


def _task(path: str, owner: str = "gameplay_programmer", tid: str = "T9") -> Task:
    return Task(
        raw=f"- [ ] {tid} | REWRITE {Path(path).name} | @{owner} | -> {path}",
        task_id=tid,
        owner=owner,
        mode=WriteMode.REWRITE,
        target_path=path,
        requires_file=True,
        description=f"REWRITE {Path(path).name}",
    )


def _seed_prompt_root(root: Path, *, n_tz: int = 30) -> None:
    (root / "AGENTS.md").write_text(
        "# Agents\n### @gameplay_programmer\nWrite Luau.\n"
        "### @client_programmer\nClient UI.\n",
        encoding="utf-8",
    )
    lines = ["# TZ", "## AGENT"]
    for i in range(n_tz):
        lines.append(
            f"- [ ] T{i} | long task description number {i} for padding | "
            f"@gameplay_programmer | -> src/pad{i}.luau"
        )
    lines += ["", "## HUMAN", "- [ ] H1 | smoke | @human", ""]
    (root / "PROJECT_TZ.md").write_text("\n".join(lines), encoding="utf-8")
    (root / "state.json").write_text("{}", encoding="utf-8")
    skills = root / "skills" / "compact"
    for sid in ("forge-player-attrs", "forge-luau-touch"):
        d = skills / sid
        d.mkdir(parents=True)
        (d / "card.json").write_text(
            json.dumps(
                {
                    "id": sid,
                    "exports": ["get_player_coins()", "touch_hook()"],
                    "forbid": ["wait()"],
                    "attrs": ["Coins", "Checkpoint"],
                }
            ),
            encoding="utf-8",
        )
        (d / "rules.md").write_text("use player attrs\ntouch safely\n", encoding="utf-8")


class TestA33PromptSlim(unittest.TestCase):
    def test_server_prompt_one_template_no_skills_tz_compact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_prompt_root(root)
            path = "src/server/Gameplay/Checkpoints.server.luau"
            p = root / path
            p.parent.mkdir(parents=True)
            p.write_text("--!strict\nprint(1)\n", encoding="utf-8")
            # A34 relevant_paths also wants Remotes beside target
            rem = root / "src/shared/Gameplay/Remotes.luau"
            rem.parent.mkdir(parents=True, exist_ok=True)
            rem.write_text("return {}\n", encoding="utf-8")
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    _task(path),
                    attempt=1,
                    is_7b=False,
                    num_ctx=4096,
                    num_predict=1024,
                    prompt_budget_tokens=3000,
                )
            self.assertNotIn("forge-player-attrs", prompt)
            self.assertNotIn("forge-luau-touch", prompt)
            titles = [
                ln
                for ln in prompt.splitlines()
                if ln.startswith("===")
                and (
                    "TEMPLATE" in ln
                    or "GENERATOR RULES" in ln
                    or "PUZZLES RULES" in ln
                    or "VOID RULES" in ln
                )
            ]
            self.assertEqual(len(titles), 1, titles)
            self.assertIn("CHECKPOINTS TEMPLATE", titles[0])
            # A34/A27.0: first 8 TZ lines + current task (not A33 last-5 / H1)
            tz_idx = prompt.find("PROJECT_TZ.md (compact)")
            self.assertGreater(tz_idx, 0)
            next_sec = prompt.find("\n===", tz_idx + 10)
            tz_chunk = prompt[tz_idx:next_sec]
            self.assertIn("# TZ", tz_chunk)
            self.assertIn("T9 |", tz_chunk)
            self.assertNotIn("T29 |", tz_chunk)
            toks = llm_backends.estimate_tokens(prompt)
            self.assertLessEqual(toks, 1800, f"prompt too large: {toks}")

    def test_client_keeps_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_prompt_root(root)
            path = "src/client/HUD.client.luau"
            p = root / path
            p.parent.mkdir(parents=True)
            p.write_text("--!strict\nprint(1)\n", encoding="utf-8")
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "client_programmer",
                    _task(path, owner="client_programmer"),
                    attempt=1,
                    is_7b=False,
                    num_ctx=4096,
                    num_predict=1024,
                    prompt_budget_tokens=3000,
                )
            self.assertTrue(
                "forge-player-attrs" in prompt or "forge-luau-touch" in prompt or "SKILL" in prompt.upper()
                or "player attrs" in prompt.lower()
                or "Coins" in prompt,
                "client prompt should include skills bundle content",
            )


class TestA33RepairCtx4096(unittest.TestCase):
    def test_models_json_repair_refactorer_ctx(self):
        cfg = load_model_config()
        repair = cfg.get("repair") or {}
        # A35: repair 7B 5120; refactorer stays 4096
        self.assertEqual(int(repair["ctx"]), 5120)
        self.assertEqual(int(repair.get("num_ctx") or repair["ctx"]), 5120)
        ref = (cfg.get("agents") or {})["refactorer"]
        self.assertEqual(int(ref["ctx"]), 4096)
        self.assertEqual(int(ref.get("num_ctx") or ref["ctx"]), 4096)


class TestA33RepairStubAccept(unittest.TestCase):
    def test_stub_with_structure_accepted(self):
        body = (
            "--!strict\n"
            "part.Touched:Connect(function(hit)\n"
            "  -- TODO: more polish\n"
            "  Remotes.CheckpointReached:FireClient(plr, idx)\n"
            "end)\n"
            "-- Respawn logic here\n"
        )
        self.assertTrue(
            repair_stub_structure_ok(body, ["stub/placeholder comment — write real code"])
        )

    def test_stub_without_structure_rejected(self):
        body = "--!strict\n-- Respawn logic here\nprint(1)\n"
        self.assertFalse(
            repair_stub_structure_ok(body, ["stub/placeholder comment — write real code"])
        )

    def test_non_stub_errors_not_accepted(self):
        body = "Touched\nFireClient\n-- TODO\n"
        self.assertFalse(
            repair_stub_structure_ok(
                body,
                [
                    "stub/placeholder comment — write real code",
                    "Checkpoints.server.luau missing Humanoid.Died / LoadCharacter handling",
                ],
            )
        )


class TestA33SkipAfter3Fails(unittest.TestCase):
    def test_mark_skipped_after_three(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "state.json").write_text("{}", encoding="utf-8")
            (root / "logs").mkdir()
            path = "src/shared/Gameplay/Remotes.luau"
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n## AGENT\n"
                f"- [ ] T1 | REWRITE Remotes | @gameplay_programmer | -> {path}\n"
                f"- [ ] T2 | REWRITE Remotes again | @gameplay_programmer | -> {path}\n"
                "## HUMAN\n",
                encoding="utf-8",
            )
            self.assertFalse(maybe_skip_after_target_fails(root, path))
            self.assertFalse(maybe_skip_after_target_fails(root, path))
            self.assertTrue(maybe_skip_after_target_fails(root, path))
            self.assertTrue(state_hub.is_skipped_target(root, path))
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertNotIn(f"- [ ] T1 |", tz)
            self.assertIn("SKIPPED_FOREVER", tz)

    def test_live_ops_skips_forever_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "logs").mkdir()
            (root / "state.json").write_text("{}", encoding="utf-8")
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n## AGENT\n## HUMAN\n",
                encoding="utf-8",
            )
            path = "src/shared/Gameplay/Remotes.luau"
            state_hub.mark_as_skipped(root, path, forever=True, note="test")
            # File missing but skipped — must not enqueue
            n = enqueue_missing_expected_rewrites(root)
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertNotIn(path, tz)
            # Other missing cores may still enqueue
            self.assertGreaterEqual(n, 0)

    def test_next_task_skips_forever_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "logs").mkdir()
            (root / "state.json").write_text("{}", encoding="utf-8")
            path = "src/shared/Gameplay/Remotes.luau"
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n## AGENT\n"
                f"- [ ] T1 | REWRITE Remotes | @gameplay_programmer | -> {path}\n"
                "- [ ] T2 | REWRITE Coins | @gameplay_programmer | "
                "-> src/server/Gameplay/Coins.server.luau\n",
                encoding="utf-8",
            )
            state_hub.mark_as_skipped(root, path, forever=True)
            orch = Orchestrator(root, dry_run=True)
            task = orch.next_task()
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.task_id, "T2")


class TestA33SeededRemotesPass(unittest.TestCase):
    def test_seeded_remotes_validator_pass(self):
        self.assertTrue(REMOTES.is_file(), REMOTES)
        ok, errs = validate_file(REMOTES, root=ROOT)
        self.assertTrue(ok, errs)
        text = REMOTES.read_text(encoding="utf-8")
        self.assertIn("getOrCreate", text)
        self.assertIn("local Remotes = {", text)
        self.assertIn("return Remotes", text)
        self.assertNotIn("return folder", text)


if __name__ == "__main__":
    unittest.main()
