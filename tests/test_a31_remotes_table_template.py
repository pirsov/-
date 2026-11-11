#!/usr/bin/env python3
"""A31 — Remotes exact-copy table template + anti-oscillation repair."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge.prompts import (
    EXACT_COPY_INSTRUCTION,
    FIRST_ERROR_ONLY_INSTRUCTION,
    REMOTES_EXACT_COPY,
    REMOTES_MINI_TEMPLATE,
    REMOTES_SHAPE_ONE_LINER,
    build_prompt,
    format_validator_checklist,
    is_remotes_target,
    remotes_combined_repair_message,
    repair_errors_for_7b,
)
from forge.task_parser import Task, WriteMode
from forge.validator import validate_file

REMOTES_PATH = "src/shared/Gameplay/Remotes.luau"

VALID_REMOTES = """--!strict
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

FOLDER_AS_REMOTES = """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Remotes = Instance.new("Folder")
Remotes.Name = "Remotes"
Remotes.Parent = ReplicatedStorage
return Remotes
"""

MISSING_EVENTS = """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local folder = ReplicatedStorage:FindFirstChild("Remotes")
if not folder then
	folder = Instance.new("Folder")
	folder.Name = "Remotes"
	folder.Parent = ReplicatedStorage
end
local Remotes = {
	Checkpoint = folder,
}
return Remotes
"""


def _remotes_task() -> Task:
    return Task(
        raw=(
            f"- [ ] T139 | REWRITE Remotes.luau: Create from scratch using template "
            f"| @gameplay_programmer | -> {REMOTES_PATH}"
        ),
        task_id="T139",
        owner="gameplay_programmer",
        mode=WriteMode.REWRITE,
        target_path=REMOTES_PATH,
        requires_file=True,
        description="REWRITE Remotes.luau: Create from scratch using template",
    )


def _seed_root(root: Path) -> None:
    (root / "AGENTS.md").write_text(
        "# Agents\n### @gameplay_programmer\nWrite Luau.\n",
        encoding="utf-8",
    )
    (root / "PROJECT_TZ.md").write_text(
        "# TZ\n" + _remotes_task().raw + "\n",
        encoding="utf-8",
    )
    (root / "state.json").write_text("{}", encoding="utf-8")


class TestRemotesExactCopyTemplate(unittest.TestCase):
    def test_remotes_prompt_has_exact_copy_and_table_pattern(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    _remotes_task(),
                    prompt_budget_tokens=4000,
                )
            self.assertIn(EXACT_COPY_INSTRUCTION, prompt)
            self.assertIn(REMOTES_EXACT_COPY, prompt)
            self.assertIn("=== REMOTES TEMPLATE", prompt)
            self.assertIn(REMOTES_PATH, prompt)
            # Full table pattern must survive local Ollama (not one-liner collapse)
            self.assertIn("local folder =", prompt)
            self.assertIn("getOrCreate", prompt)
            self.assertIn("local Remotes = {", prompt)
            self.assertIn("CheckpointReached = getOrCreate", prompt)
            self.assertIn("CoinCollected = getOrCreate", prompt)
            self.assertIn("return Remotes", prompt)
            self.assertIn("NEVER Remotes = folder", prompt)

    def test_remotes_strict_rules_in_prompt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _seed_root(root)
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    _remotes_task(),
                    prompt_budget_tokens=4000,
                )
            self.assertIn("NEVER Remotes = folder", prompt)
            self.assertIn("getOrCreate", prompt)
            self.assertIn("CheckpointReached", prompt)
            self.assertIn("CoinCollected", prompt)
            self.assertTrue(
                "Remotes.luau STRICT" in prompt or "NEVER set Remotes = folder" in prompt,
                "expected Remotes STRICT / HARD CAPS",
            )

    def test_non_remotes_skips_remotes_template_block(self):
        task = Task(
            raw="- [ ] T5 | REWRITE Void | @gameplay_programmer | -> src/server/Gameplay/Void.server.luau",
            task_id="T5",
            owner="gameplay_programmer",
            mode=WriteMode.REWRITE,
            target_path="src/server/Gameplay/Void.server.luau",
            requires_file=True,
            description="REWRITE Void",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
            (root / "PROJECT_TZ.md").write_text("# TZ\n" + task.raw + "\n", encoding="utf-8")
            (root / "state.json").write_text("{}", encoding="utf-8")
            with patch("forge.llm.backend_name", return_value="ollama"):
                prompt = build_prompt(
                    root,
                    "gameplay_programmer",
                    task,
                    prompt_budget_tokens=4000,
                )
            self.assertNotIn("=== REMOTES TEMPLATE", prompt)


class TestRemotesValidatorSamples(unittest.TestCase):
    def test_valid_remotes_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Remotes.luau"
            p.write_text(VALID_REMOTES, encoding="utf-8")
            ok, errs = validate_file(p)
            self.assertTrue(ok, errs)

    def test_folder_as_remotes_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Remotes.luau"
            p.write_text(FOLDER_AS_REMOTES, encoding="utf-8")
            ok, errs = validate_file(p)
            self.assertFalse(ok)
            joined = " ".join(errs)
            self.assertTrue(
                "table" in joined.lower() or "folder" in joined.lower(),
                errs,
            )

    def test_missing_events_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Remotes.luau"
            p.write_text(MISSING_EVENTS, encoding="utf-8")
            ok, errs = validate_file(p)
            self.assertFalse(ok)
            joined = " ".join(errs)
            self.assertTrue(
                "CheckpointReached" in joined or "CoinCollected" in joined or "getOrCreate" in joined,
                errs,
            )

    def test_soft_validator_keeps_remotes_checks_on(self):
        """A22.1 soft mode must NOT disable Remotes table/events checks."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Remotes.luau"
            p.write_text(FOLDER_AS_REMOTES, encoding="utf-8")
            ok, errs = validate_file(p)
            self.assertFalse(ok)
            self.assertTrue(
                any("table" in e.lower() or "folder" in e.lower() for e in errs),
                errs,
            )
            p.write_text(MISSING_EVENTS, encoding="utf-8")
            ok2, errs2 = validate_file(p)
            self.assertFalse(ok2)
            self.assertTrue(
                any(
                    k in " ".join(errs2)
                    for k in ("CheckpointReached", "CoinCollected", "getOrCreate")
                ),
                errs2,
            )


class TestRemotesRepairAntiOscillation(unittest.TestCase):
    def test_is_remotes_target(self):
        self.assertTrue(is_remotes_target(REMOTES_PATH))
        self.assertTrue(is_remotes_target("Remotes.luau"))
        self.assertFalse(is_remotes_target("Coins.server.luau"))
        self.assertFalse(is_remotes_target(None))

    def test_combined_when_table_and_missing(self):
        errs = [
            "Remotes.luau: variable Remotes must be a table { Checkpoint=..., ... }, "
            "not the Folder instance (use local folder = ... for the Folder)",
            "Remotes.luau missing CheckpointReached",
            "Remotes.luau missing CoinCollected",
            "Remotes.luau must create-or-reuse RemoteEvents (getOrCreate/FindFirstChild)",
            "[skeleton network_remote@v1] missing required `getOrCreate`",
        ]
        out = repair_errors_for_7b(errs, target_path=REMOTES_PATH)
        self.assertEqual(len(out), 1)
        self.assertIn(REMOTES_SHAPE_ONE_LINER[:40], out[0])
        self.assertIn("getOrCreate", out[0])
        self.assertIn("local Remotes = {", out[0])
        self.assertIn("return Remotes", out[0])
        self.assertIn("NEVER Remotes = folder", out[0])

        checklist = format_validator_checklist(
            errs, first_only=True, target_path=REMOTES_PATH
        )
        self.assertIn("anti-oscillation", checklist)
        self.assertNotIn(FIRST_ERROR_ONLY_INSTRUCTION, checklist)
        self.assertIn("getOrCreate", checklist)
        self.assertIn(REMOTES_MINI_TEMPLATE.strip().splitlines()[0], checklist)

    def test_non_remotes_still_first_only(self):
        errs = ["err-a", "err-b", "err-c"]
        self.assertEqual(
            repair_errors_for_7b(errs, target_path="Coins.server.luau"),
            ["err-a"],
        )
        text = format_validator_checklist(
            errs, first_only=True, target_path="Coins.server.luau"
        )
        self.assertIn(FIRST_ERROR_ONLY_INSTRUCTION, text)
        self.assertIn("1. err-a", text)
        self.assertNotIn("2. err-b", text)

    def test_combined_message_helper(self):
        msg = remotes_combined_repair_message(["table", "CheckpointReached"])
        self.assertIn("REQUIRED SHAPE", msg)
        self.assertIn("local folder =", msg)
        self.assertIn("CoinCollected", msg)


class TestNetworkRemoteSkeletonMeta(unittest.TestCase):
    def test_v1_meta_requires_events_and_forbids_folder_assign(self):
        import json

        root = Path(__file__).resolve().parents[1]
        meta = json.loads(
            (root / "skeletons/network_remote/v1/META.json").read_text(encoding="utf-8")
        )
        req = meta.get("required") or []
        self.assertIn("getOrCreate", req)
        self.assertIn("CheckpointReached", req)
        self.assertIn("CoinCollected", req)
        forbid_re = " ".join(meta.get("forbid_regex") or [])
        self.assertIn("return", forbid_re)
        self.assertIn("folder", forbid_re)
        self.assertIn("Remotes", forbid_re)

    def test_v1_skeleton_has_table_pattern(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "skeletons/network_remote/v1/SKELETON.luau").read_text(
            encoding="utf-8"
        )
        self.assertIn("local folder =", text)
        self.assertIn("getOrCreate", text)
        self.assertIn("local Remotes = {", text)
        self.assertIn("CheckpointReached", text)
        self.assertIn("CoinCollected", text)
        self.assertIn("return Remotes", text)
        self.assertNotIn("local Remotes = folder", text)


if __name__ == "__main__":
    unittest.main()
