#!/usr/bin/env python3
"""A30 — Live Ops local missing REWRITE enqueue without DeepSeek invent."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from forge import deepseek
from forge.orchestrator import (
    EXPECTED_GAME_FILES,
    enqueue_missing_expected_rewrites,
    missing_expected_game_files,
    run_loop,
    try_live_ops_more_tasks,
)


def _seed_partial_cores(root: Path, *, prior_template_done: bool = False) -> None:
    """LevelConfig/Coins/HUD/Effects/PlayerData present; 6 cores missing (score ~70)."""
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / ".forge").mkdir(parents=True, exist_ok=True)
    (root / "projects" / "game1").mkdir(parents=True, exist_ok=True)
    (root / ".forge" / "active_project.json").write_text(
        json.dumps({"id": "game1"}), encoding="utf-8"
    )
    (root / "projects" / "game1" / "meta.json").write_text(
        json.dumps({"id": "game1", "title": "Horror coins"}),
        encoding="utf-8",
    )
    present = [
        "src/shared/Content/LevelConfig.luau",
        "src/server/Gameplay/Coins.server.luau",
        "src/client/HUD.client.luau",
        "src/client/Effects.client.luau",
        "src/server/Data/PlayerData.server.luau",
    ]
    for rel in present:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("--!strict\n", encoding="utf-8")

    agent_lines = [
        "# LAST_UPDATE: game1",
        "",
        "## AGENT",
        "- [x] T1 | REWRITE LevelConfig | @gameplay_programmer | "
        "-> src/shared/Content/LevelConfig.luau",
        "- [x] T12 | REWRITE QA | @qa_engineer | -> docs/QA_REPORT.md",
    ]
    if prior_template_done:
        # Prior Live Ops marked template REWRITEs done but files still absent.
        for i, rel in enumerate(EXPECTED_GAME_FILES, start=20):
            if rel in present:
                continue
            fname = Path(rel).name
            agent_lines.append(
                f"- [x] T{i} | REWRITE {fname}: Create from scratch using template "
                f"| @gameplay_programmer | -> {rel}"
            )
    agent_lines += ["", "## HUMAN", "- [x] H1 | smoke | @human", ""]
    (root / "PROJECT_TZ.md").write_text("\n".join(agent_lines), encoding="utf-8")
    (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (root / "state.json").write_text(
        json.dumps({"pulse": {"cycle": 1}, "task_queue": [], "done": []}),
        encoding="utf-8",
    )


class TestEnqueueMissingLocal(unittest.TestCase):
    def test_enqueue_without_deepseek(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_partial_cores(root)
            missing = missing_expected_game_files(root)
            self.assertGreaterEqual(len(missing), 6)
            with patch.object(deepseek, "chat") as chat_mock:
                n = enqueue_missing_expected_rewrites(root)
            chat_mock.assert_not_called()
            self.assertEqual(n, len(missing))
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("Create from scratch using template", tz)
            self.assertIn("-> src/shared/Gameplay/Remotes.luau", tz)
            self.assertIn("-> src/server/InitRemotes.server.luau", tz)
            self.assertIn("-> src/server/Level/Generator.server.luau", tz)

    def test_redo_after_done_template_descs(self):
        """Desc-dedupe must not block re-queue when file still missing."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_partial_cores(root, prior_template_done=True)
            with patch.object(deepseek, "available", return_value=True), patch.object(
                deepseek, "chat", return_value=""
            ) as chat_mock:
                n = try_live_ops_more_tasks(root)
            chat_mock.assert_not_called()
            self.assertGreater(n, 0)
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            pending = [ln for ln in tz.splitlines() if ln.startswith("- [ ] T")]
            self.assertTrue(pending)
            self.assertTrue(all("Create from scratch using template" in ln for ln in pending))

    def test_deepseek_empty_still_enqueues_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_partial_cores(root)
            with patch.object(deepseek, "available", return_value=True), patch.object(
                deepseek, "chat", return_value="nope not tasks"
            ) as chat_mock:
                n = try_live_ops_more_tasks(root)
            # Missing cores => DeepSeek invent must not run
            chat_mock.assert_not_called()
            self.assertGreater(n, 0)

    def test_deepseek_fail_week_continues_with_local_rewrites(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_partial_cores(root, prior_template_done=True)
            from forge.orchestrator import next_tz_id_number

            missing = missing_expected_game_files(root)
            start = next_tz_id_number((root / "PROJECT_TZ.md").read_text(encoding="utf-8"))
            first_id = f"T{start}"
            first_path = missing[0]
            good = (
                f"<DONE>{first_id}</DONE>\n<NOTE>ok</NOTE>\n"
                f'<FILE path="{first_path}">\n'
                "--!strict\nreturn {}\n</FILE>\n"
            )
            with patch.object(deepseek, "available", return_value=True), patch.object(
                deepseek, "chat", return_value=""
            ), patch(
                "forge.orchestrator.validate_file", return_value=(True, [])
            ), redirect_stdout(io.StringIO()) as buf:
                completed = run_loop(
                    root,
                    max_steps=2,
                    sleep_s=0,
                    week=True,
                    mock_responses={first_id: [good]},
                )
            out = buf.getvalue()
            self.assertIn("[Live Ops] Tasks exhausted. Generated", out)
            self.assertIn("Continuing.", out)
            self.assertNotIn("DeepSeek could not invent new tasks. Stopping.", out)
            self.assertGreaterEqual(completed, 1)
            self.assertNotIn("…", out)


class TestModelsJsonA29StillClean(unittest.TestCase):
    def test_no_stealth_space_bunny_agent_tag(self):
        raw = (Path(__file__).resolve().parents[1] / "forge" / "models.json").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("stealth/space-bunny-alpha", raw)
        data = json.loads(raw)
        agents = data["agents"]
        self.assertEqual(agents["gameplay_programmer"]["model"], "qwen2.5-coder:14b-4k")
        self.assertEqual(agents["gameplay_programmer"].get("num_ctx"), 4096)
        self.assertEqual(agents["refactorer"]["model"], "qwen2.5-coder:7b-2k")


class TestChecklistSurfacesRoleCtx(unittest.TestCase):
    def test_token_economy_detail_mentions_gameplay_num_ctx(self):
        from forge import launch_checklist

        report = launch_checklist.build_checklist(Path(__file__).resolve().parents[1])
        detail = report["checks"]["token_economy"]["detail"]
        self.assertIn("ctx=2048", detail)
        self.assertIn("gameplay/client num_ctx=4096", detail)
        self.assertEqual(report["checks"]["token_economy"].get("gameplay_num_ctx"), 4096)


if __name__ == "__main__":
    unittest.main()
