"""Uninstall every mod of a game from the mods screen (U, :uninstall-all)."""

import json
import unittest

from textual.widgets import Input

from omamods.game_revert import GameRevert, RecordRevert
from omamods.nexus_api import NexusFile
from omamods.staging import StagedMod
from omamods.tui.app import OmaModsApp
from omamods.tui.dialogs import ConfirmDialog
from omamods.tui.uninstall_all_actions import describe_installed, summarize_revert
from tests.test_tui import TuiFixture


def staged(mod_id: int, installed: frozenset[int], site: str = "nexus") -> StagedMod:
    files = tuple(NexusFile(i, f"f{i}.zip", "MAIN", 1) for i in installed)
    return StagedMod(mod_id, None, files, {}, None, installed, site)


class UninstallAllTextTests(unittest.TestCase):
    def test_dialog_lists_each_mod_and_the_total(self) -> None:
        mods = (staged(1, frozenset({7, 8})), staged(2, frozenset({9}), "ayaka"))
        text = describe_installed(mods)
        self.assertIn("  Mod 1: 2 file(s)", text)
        self.assertIn("  Mod 2: 1 file(s)", text)
        self.assertTrue(text.endswith("Total: 3 installed file(s) in 2 mod(s)"))

    def test_summary_names_failures_by_title_and_file(self) -> None:
        outcome = GameRevert(
            (
                RecordRevert("nexus", 1, 7, 3),
                RecordRevert("ayaka", 2, 9, 0, "file changed"),
                RecordRevert("ayaka", 4, None, 0, "bad record"),
            )
        )
        text = summarize_revert(outcome, {("ayaka", 2): "Hair"})
        self.assertTrue(text.startswith("Removed 3 files from 1 mods; 2 failed:"))
        self.assertIn("Hair file 9: file changed", text)
        self.assertIn("mod 4: bad record", text)

    def test_summary_without_failures_is_one_line(self) -> None:
        outcome = GameRevert((RecordRevert("nexus", 1, 7, 3),))
        self.assertEqual(summarize_revert(outcome, {}), "Removed 3 files from 1 mods")


class UninstallAllTuiTests(TuiFixture):
    def _messages(self, app: OmaModsApp) -> list[str]:
        return [str(notification.message) for notification in app._notifications]

    def _record_broken_ayaka_mod(self) -> None:
        """Record Ayaka mod 2 file 9 with an invalid digest, so revert refuses it."""
        (self.root / "store/ayaka/archives/stellar-blade/2").mkdir(parents=True)
        utoc = self.paks / "~mods/Other_P.utoc"
        utoc.parent.mkdir(parents=True, exist_ok=True)
        utoc.write_bytes(b"utoc")
        record = self.root / "store/ayaka/state/stellar-blade/2/9.json"
        record.parent.mkdir(parents=True)
        owned = {"relative_path": "~mods/Other_P.utoc", "sha256": "x"}
        record.write_text(json.dumps({"paks": str(self.paks), "assets": [owned]}))

    async def test_u_reverts_every_mod_and_reports_failures(self) -> None:
        app = self._app({"Black/s.pak": b"pak"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await pilot.press("i", "y")
            await app.workers.wait_for_complete()
            self._record_broken_ayaka_mod()
            app.screen.reload()
            await pilot.press("U")
            self.assertIsInstance(app.screen, ConfirmDialog)
            self.assertIn("in 2 mod(s)", app.screen.details)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertFalse((self.paks / "~mods/Black/s.pak").exists())
            self.assertTrue((self.paks / "~mods/Other_P.utoc").exists())
            summary = [m for m in self._messages(app) if m.startswith("Removed 1")]
            self.assertIn("Removed 1 files from 1 mods; 1 failed:", summary[0])
            self.assertIn("Mod 2 file 9: owned SHA-256='x'", summary[0])

    async def test_command_with_nothing_installed_only_notifies(self) -> None:
        app = self._app({"Black/s.pak": b"pak"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await pilot.press("colon")
            app.screen.query_one(Input).value = "uninstall-all"
            await pilot.press("enter")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, ConfirmDialog)
            self.assertIn(
                "Nothing is installed for Stellar Blade.", self._messages(app)
            )


if __name__ == "__main__":
    unittest.main()
