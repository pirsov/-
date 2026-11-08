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

    def test_fix_mode_is_rewrite(self):
        line = '- [ ] P30.2 | Fix HIGH/CRIT from latest QA_REPORT | @refactorer'
        t = parse_task_line(line)
        assert t is not None
        self.assertEqual(t.mode, WriteMode.REWRITE)

    def test_section_anchor(self):
        line = '- [ ] P1.1 | Define genre | @game_designer | → docs/GDD.md#core-loop'
        t = parse_task_line(line)
        assert t is not None
        self.assertEqual(t.target_path, "docs/GDD.md")
        self.assertEqual(t.section, "core-loop")

    def test_week_human_task_parsed(self):
        line = '- [ ] W1.5 | Studio smoke baseline (CP, coin, void, plate) | @human'
        t = parse_task_line(line)
        assert t is not None
        self.assertEqual(t.task_id, "W1.5")
        self.assertEqual(t.owner, "human")

    def test_agent_sprint_id_parsed(self):
        line = (
            "- [ ] A1 | REWRITE Generator.server.luau: add obstacles | "
            "@gameplay_programmer | → src/server/Level/Generator.server.luau"
        )
        t = parse_task_line(line)
        assert t is not None
        self.assertEqual(t.task_id, "A1")
        self.assertEqual(t.owner, "gameplay_programmer")
        self.assertEqual(t.mode, WriteMode.REWRITE)
        self.assertEqual(t.target_path, "src/server/Level/Generator.server.luau")

    def test_z_sprint_id_parsed(self):
        line = (
            "- [ ] Z1 | REWRITE Generator from baseline seed | "
            "@gameplay_programmer | → src/server/Level/Generator.server.luau"
        )
        t = parse_task_line(line)
        assert t is not None
        self.assertEqual(t.task_id, "Z1")


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

    def test_parse_sprint_done_a1(self):
        out = (
            "<DONE>A1</DONE>\n<NOTE>obstacles</NOTE>\n"
            '<FILE path="src/server/Level/Generator.server.luau">\n--!strict\nprint(1)\n</FILE>\n'
        )
        done, note, files, blocked = parse_agent_output(out, "A1")
        self.assertEqual(done, "A1")
        self.assertEqual(note, "obstacles")
        self.assertEqual(len(files), 1)
        self.assertIsNone(blocked)

    def test_parse_sloppy_done_a3(self):
        out = (
            "DONE>A3\n<NOTE>map</NOTE>\n"
            '<FILE path="docs/GDD.md">\n# Map\n</FILE>\n'
        )
        done, note, files, _ = parse_agent_output(out, "A3")
        self.assertEqual(done, "A3")
        self.assertEqual(len(files), 1)


class TestModelResolve(unittest.TestCase):
    def test_remap_bare_tag_to_custom(self):
        from forge.ollama_client import resolve_model

        installed = ["qwen2.5-coder:7b-2k", "qwen2.5-coder:3b-8k", "qwen2.5-coder:14b-4k"]
        self.assertEqual(resolve_model("qwen2.5-coder:7b", installed), "qwen2.5-coder:7b-2k")
        self.assertEqual(resolve_model("qwen2.5-coder:14b", installed), "qwen2.5-coder:14b-4k")
        self.assertEqual(resolve_model("qwen2.5-coder:3b-8k", installed), "qwen2.5-coder:3b-8k")


class TestHitlPrompt(unittest.TestCase):
    def test_resolve_hitl_choice(self):
        from forge.orchestrator import resolve_hitl_choice
        import os

        old = os.environ.get("FORGE_HITL_AUTO")
        try:
            os.environ.pop("FORGE_HITL_AUTO", None)
            self.assertIsNone(resolve_hitl_choice(auto=None))
            self.assertTrue(resolve_hitl_choice(auto="y"))
            self.assertFalse(resolve_hitl_choice(auto="n"))
            os.environ["FORGE_HITL_AUTO"] = "y"
            self.assertTrue(resolve_hitl_choice(auto=None))
        finally:
            if old is None:
                os.environ.pop("FORGE_HITL_AUTO", None)
            else:
                os.environ["FORGE_HITL_AUTO"] = old

    def test_hitl_y_marks_done(self):
        from forge.orchestrator import Orchestrator

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n- [ ] W1.5 | Studio smoke | @human\n- [ ] W2.1 | next | @game_designer\n",
                encoding="utf-8",
            )
            (root / "src").mkdir()
            orch = Orchestrator(root, hitl_auto="y")
            result = orch.invoke_step()
            self.assertTrue(result.ok)
            self.assertEqual(result.reason, "human_ok")
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("- [x] W1.5", tz)

    def test_hitl_n_stops(self):
        from forge.orchestrator import Orchestrator

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "PROJECT_TZ.md").write_text(
                "# TZ\n- [ ] W1.5 | Studio smoke | @human\n",
                encoding="utf-8",
            )
            (root / "src").mkdir()
            orch = Orchestrator(root, hitl_auto="n")
            result = orch.invoke_step()
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "human")
            tz = (root / "PROJECT_TZ.md").read_text(encoding="utf-8")
            self.assertIn("- [ ] W1.5", tz)


class TestLlmAuthHelpers(unittest.TestCase):
    def test_clean_key_strips_quotes(self):
        from forge.llm import _clean_key

        self.assertEqual(_clean_key("  'sk-or-v1-abc'  "), "sk-or-v1-abc")
        self.assertEqual(_clean_key('"sb_live_x"'), "sb_live_x")


class TestLlmBackend(unittest.TestCase):
    def test_auto_spacebunny_when_key_set(self):
        import os
        from forge import llm

        old = {k: os.environ.get(k) for k in ("FORGE_BACKEND", "SPACE_BUNNY_API_KEY", "OPENROUTER_API_KEY")}
        try:
            os.environ.pop("FORGE_BACKEND", None)
            os.environ.pop("OPENROUTER_API_KEY", None)
            os.environ["SPACE_BUNNY_API_KEY"] = "sb_live_test"
            self.assertEqual(llm.backend_name(), "spacebunny")
            self.assertEqual(llm.resolve_model("anything"), "space-bunny-alpha")
            self.assertTrue(llm.ping())
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_explicit_openrouter(self):
        import os
        from forge import llm

        old = {k: os.environ.get(k) for k in ("FORGE_BACKEND", "SPACE_BUNNY_API_KEY", "OPENROUTER_API_KEY")}
        try:
            os.environ["FORGE_BACKEND"] = "openrouter"
            os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
            self.assertEqual(llm.backend_name(), "openrouter")
            self.assertEqual(llm.resolve_model("x"), "stealth/space-bunny-alpha")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class TestRemotesValidator(unittest.TestCase):
    def test_accept_table_return_remotes(self):
        from forge.validator import validate_file

        good = """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local folder = ReplicatedStorage:FindFirstChild("Remotes")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Remotes"
	folder.Parent = ReplicatedStorage
end
local function getOrCreate(name: string): RemoteEvent
	local r = folder:FindFirstChild(name)
	if not r then
		r = Instance.new("RemoteEvent")
		r.Name = name
		r.Parent = folder
	end
	return r :: RemoteEvent
end
local Remotes = {
	Checkpoint = getOrCreate("Checkpoint"),
	CheckpointReached = getOrCreate("CheckpointReached"),
	UpdateLeaderboard = getOrCreate("UpdateLeaderboard"),
	CoinCollected = getOrCreate("CoinCollected"),
}
return Remotes
"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Remotes.luau"
            p.write_text(good, encoding="utf-8")
            ok, errs = validate_file(p)
            self.assertTrue(ok, errs)

    def test_reject_return_folder(self):
        from forge.validator import validate_file

        bad = """--!strict
local folder = Instance.new("Folder")
folder.Name = "Remotes"
return folder
"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Remotes.luau"
            p.write_text(bad, encoding="utf-8")
            ok, errs = validate_file(p)
            self.assertFalse(ok)
            self.assertTrue(any("folder" in e.lower() or "table" in e.lower() for e in errs), errs)


class TestValidatorGuards(unittest.TestCase):
    def test_reject_stub_checkpoints_and_playerrespawn(self):
        from forge.validator import validate_file

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Checkpoints.server.luau"
            p.write_text(
                "--!strict\n"
                "local Remotes = require(game.ReplicatedStorage.Gameplay.Remotes)\n"
                "Remotes.PlayerRespawn.OnServerEvent:Connect(function()\n"
                "  -- Respawn logic here\n"
                "end)\n"
                "Remotes.CheckpointReached.OnServerEvent:Connect(function() end)\n",
                encoding="utf-8",
            )
            ok, errs = validate_file(p)
            self.assertFalse(ok)
            joined = " ".join(errs)
            self.assertIn("PlayerRespawn", joined)
            self.assertIn("stub", joined.lower())
            self.assertIn("Touched", joined)

    def test_remotes_path_segment_not_false_positive(self):
        from forge.validator import validate_file

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Remotes.luau"
            p.write_text(
                "--!strict\n"
                "local folder = game.ReplicatedStorage:FindFirstChild(\"Remotes\")\n"
                "local function getOrCreate(name) return Instance.new(\"RemoteEvent\") end\n"
                "return {\n"
                "  Checkpoint = getOrCreate(\"Checkpoint\"),\n"
                "  CheckpointReached = getOrCreate(\"CheckpointReached\"),\n"
                "  UpdateLeaderboard = getOrCreate(\"UpdateLeaderboard\"),\n"
                "}\n",
                encoding="utf-8",
            )
            ok, errs = validate_file(p)
            self.assertTrue(ok, errs)

    def test_qa_allows_playerrespawn_disclaimer_not_bug(self):
        from forge.validator import validate_file

        with tempfile.TemporaryDirectory() as td:
            good = Path(td) / "QA_REPORT.md"
            good.write_text(
                "## BUGS\n- [LOW] unused Checkpoint remote\n\n"
                "## SCORE\n- overall: 82\n"
                "- note: Do NOT invent PlayerRespawn\n",
                encoding="utf-8",
            )
            ok, errs = validate_file(good)
            self.assertTrue(ok, errs)

            bad = Path(td) / "QA_REPORT.md"
            bad.write_text(
                "## BUGS\n"
                "- [CRIT] PlayerRespawn event does not handle death\n\n"
                "## SCORE\n- overall: 50\n",
                encoding="utf-8",
            )
            ok2, errs2 = validate_file(bad)
            self.assertFalse(ok2)
            self.assertTrue(any("PlayerRespawn" in e for e in errs2))

    def test_reject_checkpoints_setattr_part_and_hit_parent(self):
        from forge.validator import validate_file

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Checkpoints.server.luau"
            p.write_text(
                "--!strict\n"
                "local Remotes = require(game.ReplicatedStorage.Gameplay.Remotes)\n"
                "local function onCheckpointTouched(hit)\n"
                "  local cp = hit.Parent\n"
                "  plr:SetAttribute(\"Checkpoint\", cp)\n"
                "  Remotes.CheckpointReached:FireClient(plr, 1)\n"
                "end\n"
                "child.Touched:Connect(onCheckpointTouched)\n"
                "hum.Died:Connect(function() plr:LoadCharacter() end)\n",
                encoding="utf-8",
            )
            ok, errs = validate_file(p)
            self.assertFalse(ok)
            joined = " ".join(errs)
            self.assertIn("idx", joined.lower() + "number")
            self.assertTrue(
                "hit.Parent" in joined or "SetAttribute" in joined or "number" in joined,
                errs,
            )


if __name__ == "__main__":
    unittest.main()
