#!/usr/bin/env python3
"""A34 — gap-fill A27.0 Max Context & Prompt Slimming (beyond A33)."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from forge import llm_backends
from forge.orchestrator import Orchestrator, pick_model
from forge.prompts import (
    REPAIR_FIX_INSTRUCTION,
    build_prompt,
    extract_broken_function_snippet,
    relevant_paths,
    tz_compact_for_task,
)
from forge.task_parser import Task, WriteMode
from forge.validator import validate_file

ROOT = Path(__file__).resolve().parent.parent


def _task(
    path: str,
    owner: str = "gameplay_programmer",
    tid: str = "T9",
) -> Task:
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
        "### @client_programmer\nClient UI.\n"
        "### @qa_engineer\nReview.\n"
        "### @refactorer\nRefactor.\n",
        encoding="utf-8",
    )
    lines = ["# TZ", "## AGENT", "Intro line 3", "Intro line 4", "Intro line 5"]
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


class TestA34RelevantPaths(unittest.TestCase):
    def test_gameplay_only_target_and_remotes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = "src/server/Gameplay/Checkpoints.server.luau"
            for rel in (
                target,
                "src/shared/Gameplay/Remotes.luau",
                "src/server/Gameplay/Coins.server.luau",
                "src/server/Gameplay/Puzzles.server.luau",
                "src/client/HUD.client.luau",
                "docs/GDD.md",
            ):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("--x\n", encoding="utf-8")
            (root / "default.project.json").write_text("{}", encoding="utf-8")
            paths = relevant_paths(root, _task(target), "gameplay_programmer")
            rels = {str(p.relative_to(root)).replace("\\", "/") for p in paths}
            self.assertEqual(
                rels,
                {target, "src/shared/Gameplay/Remotes.luau"},
            )

    def test_client_only_target_and_remotes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = "src/client/HUD.client.luau"
            for rel in (
                target,
                "src/shared/Gameplay/Remotes.luau",
                "src/client/Effects.client.luau",
                "src/server/Gameplay/Coins.server.luau",
            ):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("--x\n", encoding="utf-8")
            paths = relevant_paths(
                root, _task(target, owner="client_programmer"), "client_programmer"
            )
            rels = {str(p.relative_to(root)).replace("\\", "/") for p in paths}
            self.assertEqual(rels, {target, "src/shared/Gameplay/Remotes.luau"})

    def test_qa_and_refactorer_need_all_src(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            files = [
                "src/a.luau",
                "src/b.luau",
                "src/shared/Gameplay/Remotes.luau",
            ]
            for rel in files:
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("return {}\n", encoding="utf-8")
            for owner in ("qa_engineer", "refactorer"):
                paths = relevant_paths(root, _task("src/a.luau", owner=owner), owner)
                rels = {str(p.relative_to(root)).replace("\\", "/") for p in paths}
                self.assertIn("src/a.luau", rels)
                self.assertIn("src/b.luau", rels)


class TestA34TzCompact(unittest.TestCase):
    def test_first_8_plus_current_task(self):
        lines = [f"L{i}" for i in range(20)]
        lines[10] = "- [ ] T9 | REWRITE Checkpoints | @gameplay_programmer | -> src/x.luau"
        tz = "\n".join(lines)
        task = _task("src/x.luau", tid="T9")
        compact = tz_compact_for_task(tz, task, first_n=8)
        out_lines = compact.splitlines()
        self.assertEqual(out_lines[:8], lines[:8])
        self.assertIn(lines[10], out_lines)
        self.assertNotIn("L19", compact)
        # first_n=8 → L0..L7; L8 (9th line) is NOT in head
        self.assertNotIn("\nL8\n", "\n" + compact + "\n")

    def test_build_prompt_uses_first_8_not_last_5(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_prompt_root(root, n_tz=30)
            path = "src/server/Gameplay/Checkpoints.server.luau"
            p = root / path
            p.parent.mkdir(parents=True)
            p.write_text("--!strict\nprint(1)\n", encoding="utf-8")
            rem = root / "src/shared/Gameplay/Remotes.luau"
            rem.parent.mkdir(parents=True, exist_ok=True)
            rem.write_text("return {}\n", encoding="utf-8")
            task = _task(path, tid="T9")
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    task,
                    attempt=1,
                    is_7b=False,
                    num_ctx=4096,
                    num_predict=1024,
                    prompt_budget_tokens=3000,
                )
            tz_idx = prompt.find("PROJECT_TZ.md (compact)")
            self.assertGreater(tz_idx, 0)
            # Between TZ header and next === section
            next_sec = prompt.find("\n===", tz_idx + 10)
            tz_chunk = prompt[tz_idx:next_sec]
            self.assertIn("# TZ", tz_chunk)
            self.assertIn("## AGENT", tz_chunk)
            self.assertIn("T9 |", tz_chunk)
            # Last-5 A33 behavior would include H1; first-8 may not — current task must.
            self.assertNotIn("T29 |", tz_chunk)


class TestA34RepairSnippet(unittest.TestCase):
    def test_extract_broken_function_not_whole_file(self):
        body = (
            "--!strict\n"
            "local Remotes = {}\n"
            "local function okFn()\n"
            "  return 1\n"
            "end\n"
            "local function brokenHook(part: BasePart)\n"
            "  -- TODO: implement touch\n"
            "  -- Respawn logic here\n"
            "end\n"
            "local function other()\n"
            "  print('x')\n"
            "end\n"
        )
        snip = extract_broken_function_snippet(
            body, "stub/placeholder comment — write real code"
        )
        self.assertIn("brokenHook", snip)
        self.assertIn("-- TODO", snip)
        self.assertNotIn("local function other", snip)
        self.assertLess(len(snip), len(body))

    def test_repair_mode_prompt_one_error_snippet(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_prompt_root(root, n_tz=5)
            path = "src/server/Gameplay/Checkpoints.server.luau"
            p = root / path
            p.parent.mkdir(parents=True)
            p.write_text("--!strict\nprint(1)\n", encoding="utf-8")
            draft = (
                "--!strict\n"
                "local function hookPart(part: BasePart)\n"
                "  -- TODO: more polish\n"
                "  part.Touched:Connect(function() end)\n"
                "end\n"
                + ("-- padding line\n" * 80)
            )
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    _task(path),
                    attempt=2,
                    validator_feedback=(
                        "MANDATORY: x\n"
                        "REPAIR CHECKLIST (validator_fails) — fix EVERY bullet, in order:\n"
                        "1. stub/placeholder comment — write real code\n"
                        "2. Checkpoints.server.luau missing Humanoid.Died / LoadCharacter\n"
                    ),
                    repair_draft=draft,
                    is_7b=True,
                    prompt_budget_tokens=1000,
                    num_ctx=4096,
                    num_predict=512,
                )
            idx = prompt.find("=== REPAIR MODE")
            self.assertGreaterEqual(idx, 0)
            # Until YOUR TASK or end
            next_sec = prompt.find("\n=== YOUR TASK", idx)
            block = prompt[idx : next_sec if next_sec > 0 else idx + 2000]
            self.assertIn("Error:", block)
            self.assertIn("stub/placeholder", block)
            self.assertNotIn("missing Humanoid.Died", block)  # only ONE error
            self.assertIn("Broken function:", block)
            self.assertIn("hookPart", block)
            self.assertIn(REPAIR_FIX_INSTRUCTION, block)
            self.assertNotIn("-- padding line", block)
            # Whole REPAIR MODE block should stay lean (~1200+)
            self.assertLessEqual(len(block), 1600, f"repair block too large: {len(block)}")


class TestA34StubIgnoreOnRepair(unittest.TestCase):
    def test_stub_fails_normally(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "X.server.luau"
            p.write_text(
                "--!strict\n"
                "local Players = game:GetService(\"Players\")\n"
                "-- TODO: real code here\n"
                "print(Players)\n",
                encoding="utf-8",
            )
            ok, errs = validate_file(p, is_repair=False)
            self.assertFalse(ok)
            self.assertTrue(any("stub" in e.lower() for e in errs))

    def test_stub_ignored_when_is_repair(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "X.server.luau"
            p.write_text(
                "--!strict\n"
                "local Players = game:GetService(\"Players\")\n"
                "-- TODO: real code here\n"
                "-- Respawn logic here\n"
                "print(Players)\n",
                encoding="utf-8",
            )
            ok, errs = validate_file(p, is_repair=True)
            self.assertTrue(ok, errs)
            self.assertFalse(any("stub" in e.lower() for e in errs))


class TestA34RepairCtxAndLog(unittest.TestCase):
    def test_pick_model_repair_num_ctx_5120(self):
        with patch("forge.orchestrator.llm.backend_name", return_value="ollama"), patch(
            "forge.orchestrator.installed_models",
            return_value=["qwen2.5-coder:7b-2k", "qwen2.5-coder:14b-4k"],
        ), patch("forge.orchestrator.llm.resolve_model", side_effect=lambda p, *a, **k: p):
            cfg = pick_model("gameplay_programmer", attempt=2, escalate=True)
        self.assertEqual(int(cfg["ctx"]), 5120)
        self.assertEqual(int(cfg.get("num_ctx") or cfg["ctx"]), 5120)
        self.assertTrue(cfg.get("is_7b"))
        opts = llm_backends.ollama_options(
            num_ctx=cfg["ctx"], num_predict=cfg["predict"], diff_mode=True
        )
        self.assertEqual(opts["num_ctx"], 5120)

    def test_prompt_log_includes_predict(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text(
                "# Agents\n### @gameplay_programmer\nWrite Luau.\n",
                encoding="utf-8",
            )
            path = "src/server/Gameplay/Checkpoints.server.luau"
            (root / "PROJECT_TZ.md").write_text(
                f"# TZ\n## AGENT\n- [ ] T1 | REWRITE | @gameplay_programmer | -> {path}\n",
                encoding="utf-8",
            )
            (root / "state.json").write_text(
                '{"task_queue":[{"id":"T1","status":"ready"}],'
                '"open_questions":[],"pulse":{"ok":true},"done":[]}',
                encoding="utf-8",
            )
            (root / "logs").mkdir()
            target = root / path
            target.parent.mkdir(parents=True)
            target.write_text("--!strict\nprint(1)\n", encoding="utf-8")
            rem = root / "src/shared/Gameplay/Remotes.luau"
            rem.parent.mkdir(parents=True, exist_ok=True)
            rem.write_text(
                "local Remotes = { Checkpoint = 1, CheckpointReached = 1, "
                "UpdateLeaderboard = 1, CoinCollected = 1 }\n"
                "local function getOrCreate(n) end\nreturn Remotes\n",
                encoding="utf-8",
            )
            orch = Orchestrator(root, dry_run=False)
            orch.mock_responses = {
                "T1": [
                    f"<DONE>T1</DONE>\n<NOTE>ok</NOTE>\n"
                    f'<FILE path="{path}">\n--!strict\n'
                    f'local Players = game:GetService("Players")\n'
                    f"print(Players)\n</FILE>\n"
                ]
            }
            buf = io.StringIO()
            with redirect_stdout(buf), patch(
                "forge.orchestrator.llm.backend_name", return_value="ollama"
            ), patch(
                "forge.orchestrator.llm.resolve_runtime_backend",
                return_value=("ollama", "test"),
            ), patch(
                "forge.orchestrator.pick_model",
                return_value={
                    "model": "qwen2.5-coder:14b-4k",
                    "ctx": 4096,
                    "num_ctx": 4096,
                    "predict": 1024,
                    "is_7b": False,
                    "diff_mode": False,
                    "prompt_budget_tokens": 3000,
                },
            ):
                orch.invoke_step()
            out = buf.getvalue()
            self.assertRegex(
                out,
                r"prompt_tokens=\d+ / budget=\d+ / ctx=4096 / predict=1024",
            )


class TestA34SkillsServerOff(unittest.TestCase):
    def test_server_prompt_no_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_prompt_root(root, n_tz=5)
            path = "src/server/Gameplay/Checkpoints.server.luau"
            p = root / path
            p.parent.mkdir(parents=True)
            p.write_text("--!strict\nprint(1)\n", encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
