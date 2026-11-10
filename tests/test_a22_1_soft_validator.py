"""A22.1 TEMP soft validator — three strict checks disabled so files can save."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from forge.validator import validate_file


class TestA221SoftValidator(unittest.TestCase):
    def test_breakjoints_does_not_fail_while_soft(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Misc.server.luau"
            p.write_text(
                "--!strict\n"
                "local Players = game:GetService(\"Players\")\n"
                "local hum = workspace:FindFirstChild(\"Humanoid\")\n"
                "if hum then hum:BreakJoints() end\n"
                "print(\"breakjoints soft ok\")\n",
                encoding="utf-8",
            )
            _ok, errs = validate_file(p)
            self.assertNotIn("BreakJoints is deprecated", errs, errs)
            self.assertFalse(any("BreakJoints" in e for e in errs), errs)

    def test_checkpoint_part_attr_does_not_fail_while_soft(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Checkpoints.server.luau"
            p.write_text(
                "--!strict\n"
                "local Remotes = require(game.ReplicatedStorage.Gameplay.Remotes)\n"
                "local folder = workspace:FindFirstChild(\"Checkpoints\")\n"
                "part.Touched:Connect(function(hit)\n"
                "\tlocal plr = game.Players:GetPlayerFromCharacter(hit.Parent)\n"
                "\tif plr then\n"
                "\t\tplr:SetAttribute(\"Checkpoint\", part)\n"
                "\t\tRemotes.CheckpointReached:FireClient(plr, part)\n"
                "\tend\n"
                "end)\n"
                "humanoid.Died:Connect(function()\n"
                "\tlocal cp = folder:FindFirstChild(\"Checkpoint\" .. tostring(idx))\n"
                "\tplr:LoadCharacter()\n"
                "end)\n",
                encoding="utf-8",
            )
            _ok, errs = validate_file(p)
            self.assertFalse(
                any("pass numeric idx, not a Part" in e for e in errs),
                errs,
            )
            self.assertFalse(
                any('SetAttribute("Checkpoint", part)' in e for e in errs),
                errs,
            )
            self.assertFalse(
                any('must SetAttribute("Checkpoint", <number>)' in e for e in errs),
                errs,
            )

    def test_datastore_client_does_not_fail_hardcoded_while_soft(self):
        """Hardcoded A10.1 DataStoreService check is soft; no forge root/skeletons."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "HUD.client.luau"
            p.write_text(
                "--!strict\n"
                "local Players = game:GetService(\"Players\")\n"
                "local player = Players.LocalPlayer\n"
                "local Remotes = require(game.ReplicatedStorage.Gameplay.Remotes)\n"
                "local DataStoreService = game:GetService(\"DataStoreService\")\n"
                "local gui = Instance.new(\"ScreenGui\")\n"
                "gui.Parent = player:WaitForChild(\"PlayerGui\")\n"
                "Remotes.CheckpointReached.OnClientEvent:Connect(function() end)\n"
                "Remotes.CoinCollected.OnClientEvent:Connect(function() end)\n",
                encoding="utf-8",
            )
            _ok, errs = validate_file(p)  # no root → no skeleton META
            self.assertFalse(
                any("DataStoreService forbidden on client" in e for e in errs),
                errs,
            )

    def test_empty_file_still_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Empty.server.luau"
            p.write_text("\n", encoding="utf-8")
            ok, errs = validate_file(p)
            self.assertFalse(ok)
            self.assertTrue(any("empty" in e.lower() for e in errs), errs)

    def test_unbalanced_parens_still_fail(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Bad.server.luau"
            p.write_text(
                "--!strict\n"
                "local x = ((((1 + 2)\n"
                "print(\"still enough content here\")\n",
                encoding="utf-8",
            )
            ok, errs = validate_file(p)
            self.assertFalse(ok)
            self.assertTrue(any("unbalanced parentheses" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
