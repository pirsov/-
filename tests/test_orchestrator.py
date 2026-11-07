#!/usr/bin/env python3
"""Unit tests for Quality Forge bug fixes — no Ollama required."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from forge.orchestrator import Orchestrator, apply_file_ops, parse_agent_output
from forge.task_parser import WriteMode, find_pending_tasks, parse_task_line
from forge.validator import validate_file, validate_project_integrity


ROOT = Path(__file__).resolve().parent.parent


class TestTaskParser(unittest.TestCase):
    def test_append_mode_detected(self):
        line = '- [ ] P20.14 | APPEND: local timer = ... | @refactorer | → src/client/HUD.client.luau'
        t = parse_task_line(line)
        assert t is not None
        self.assertEqual(t.mode, WriteMode.APPEND)
        self.assertEqual(t.target_path, "src/client/HUD.client.luau")
        self.assertTrue(t.requires_file)

    def test_rewrite_mode(self):
        line = '- [ ] P20.20 | Rewrite src/server/Data/PlayerData.server.luau: DataStore... | @refactorer | → src/server/Data/PlayerData.server.luau'
        t = parse_task_line(line)
        assert t is not None
        self.assertEqual(t.mode, WriteMode.REWRITE)

    def test_section_anchor(self):
        line = '- [ ] P1.1 | Define genre | @game_designer | → docs/GDD.md#core-loop'
        t = parse_task_line(line)
        assert t is not None
        self.assertEqual(t.target_path, "docs/GDD.md")
        self.assertEqual(t.section, "core-loop")


class TestAppendNeverOverwrites(unittest.TestCase):
    def test_append_preserves_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "src/client/HUD.client.luau"
            path.parent.mkdir(parents=True)
            path.write_text("--!strict\nlocal screen = 1\n", encoding="utf-8")
            from forge.orchestrator import FileOp
            from forge.task_parser import Task

            task = Task(
                raw="",
                task_id="P20.14",
                owner="refactorer",
                mode=WriteMode.APPEND,
                target_path="src/client/HUD.client.luau",
                requires_file=True,
            )
            ops = [FileOp(path="src/client/HUD.client.luau", content="local timer = 2", mode=WriteMode.APPEND)]
            apply_file_ops(root, ops, task)
            text = path.read_text(encoding="utf-8")
            self.assertIn("local screen = 1", text)
            self.assertIn("local timer = 2", text)
            self.assertTrue(text.index("screen") < text.index("timer"))


class TestDoneRequiresFile(unittest.TestCase):
    def _mini_project(self, td: Path) -> Path:
        # Minimal scaffold
        for rel in (
            "AGENTS.md",
            "PROJECT_TZ.md",
            "src/shared/Gameplay/Remotes.luau",
            "src/server/Level/Generator.server.luau",
            "src/server/Gameplay/Checkpoints.server.luau",
            "src/client/HUD.client.luau",
            "src/client/Effects.client.luau",
            "src/server/Data/PlayerData.server.luau",
            "default.project.json",
        ):
            p = td / rel
            p.parent.mkdir(parents=True, exist_ok=True)

        (td / "AGENTS.md").write_text(
            "# AGENT\n\n## @refactorer\nRules:\n- fix bugs\n",
            encoding="utf-8",
        )
        (td / "PROJECT_TZ.md").write_text(
            "# LAST_UPDATE: test\n\n"
            "- [ ] P20.18 | Create src/client/Effects.client.luau with: --!strict | @refactorer | → src/client/Effects.client.luau\n",
            encoding="utf-8",
        )
        # valid stubs so integrity isn't the failure mode
        (td / "src/shared/Gameplay/Remotes.luau").write_text(
            "--!strict\nlocal ReplicatedStorage = game:GetService(\"ReplicatedStorage\")\n"
            "local folder = Instance.new(\"Folder\")\n"
            "local function getOrCreate(name)\n"
            "  local r = Instance.new(\"RemoteEvent\")\n"
            "  r.Name = name\n"
            "  r.Parent = folder\n"
            "  return r\n"
            "end\n"
            "return { Checkpoint = getOrCreate(\"Checkpoint\"), CheckpointReached = getOrCreate(\"CheckpointReached\"), UpdateLeaderboard = getOrCreate(\"UpdateLeaderboard\") }\n",
            encoding="utf-8",
        )
        for rel, body in (
            (
                "src/server/Level/Generator.server.luau",
                "--!strict\nlocal folder = workspace:FindFirstChild(\"Checkpoints\")\n"
                "if not folder then\n  folder = Instance.new(\"Folder\")\n  folder.Name = \"Checkpoints\"\n  folder.Parent = workspace\nend\n"
                "print(\"[Generator] ok\")\n",
            ),
            (
                "src/server/Gameplay/Checkpoints.server.luau",
                "--!strict\nlocal Players = game:GetService(\"Players\")\nlocal folder = workspace:WaitForChild(\"Checkpoints\")\nprint(Players, folder)\n",
            ),
            (
                "src/client/HUD.client.luau",
                "--!strict\nlocal Players = game:GetService(\"Players\")\nlocal screen = Instance.new(\"ScreenGui\")\nprint(Players, screen)\n",
            ),
            (
                "src/client/Effects.client.luau",
                "--!strict\nprint(\"effects\")\n",
            ),
            (
                "src/server/Data/PlayerData.server.luau",
                "--!strict\nlocal Players = game:GetService(\"Players\")\nprint(Players)\n",
            ),
        ):
            (td / rel).write_text(body, encoding="utf-8")
        (td / "default.project.json").write_text('{"name":"t","tree":{}}\n', encoding="utf-8")
        return td

    def test_done_without_file_does_not_complete(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._mini_project(Path(td))
            orch = Orchestrator(
                root,
                mock_responses={
                    "P20.18": [
                        "<DONE>P20.18</DONE>\n",  # bug reproduction: DONE with no FILE
                        "<DONE>P20.18</DONE>\n<NOTE>ok</NOTE>\n"
                        '<FILE path="src/client/Effects.client.luau">\n--!strict\n'
                        'local ReplicatedStorage = game:GetService("ReplicatedStorage")\n'
                        "print(ReplicatedStorage)\n</FILE>\n",
                    ]
                },
            )
            # First step should retry internally and succeed on second mock response
            result = orch.invoke_step()
            self.assertTrue(result.ok)
            text = (root / "src/client/Effects.client.luau").read_text(encoding="utf-8")
            self.assertIn("--!strict", text)
            self.assertNotIn("return Effects", text)
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("- [x] P20.18", tz)


class TestValidatorCatchesWait(unittest.TestCase):
    def test_wait_forbidden(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "PlayerData.server.luau"
            p.write_text(
                "--!strict\n"
                "task.spawn(function()\n"
                "  while true do\n"
                "    wait(60)\n"
                "  end\n"
                "end)\n",
                encoding="utf-8",
            )
            ok, errs = validate_file(p)
            self.assertFalse(ok)
            self.assertTrue(any("task.wait" in e for e in errs))


class TestParseOutput(unittest.TestCase):
    def test_parse_file_tags(self):
        out = (
            "<DONE>P20.20</DONE>\n<NOTE>hi</NOTE>\n"
            '<FILE path="src/server/Data/PlayerData.server.luau">\n--!strict\nprint(1)\n</FILE>\n'
        )
        done, note, files, blocked = parse_agent_output(out, "P20.20")
        self.assertEqual(done, "P20.20")
        self.assertEqual(note, "hi")
        self.assertEqual(len(files), 1)
        self.assertIsNone(blocked)


class TestModelResolve(unittest.TestCase):
    def test_remap_bare_tag_to_custom(self):
        from forge.ollama_client import resolve_model

        installed = ["qwen2.5-coder:7b-2k", "qwen2.5-coder:3b-8k", "qwen2.5-coder:14b-4k"]
        self.assertEqual(resolve_model("qwen2.5-coder:7b", installed), "qwen2.5-coder:7b-2k")
        self.assertEqual(resolve_model("qwen2.5-coder:14b", installed), "qwen2.5-coder:14b-4k")
        self.assertEqual(resolve_model("qwen2.5-coder:3b-8k", installed), "qwen2.5-coder:3b-8k")


if __name__ == "__main__":
    unittest.main()
