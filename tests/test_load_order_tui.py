"""Move an installed file to load last from the mods screen, and back again."""

import json
from pathlib import Path
import tempfile
import unittest

from textual.widgets import Static

from omamods.asset_collisions import ModContainer
from omamods.load_order_store import load_order_path, write_load_order
from omamods.tui.app import OmaModsApp
from omamods.tui.dialogs import ConfirmDialog
from omamods.tui.workspace import WorkspaceHints, WorkspaceStatus
from omamods.tui.load_order_choices import (
    ContainerRename,
    container_stem,
    default_renames,
    promotion,
)
from tests.pak_builders import directory_pak_bytes, utoc_bytes
from tests.test_tui import TuiFixture

JACKET = "Art/Hero/Jacket.uasset"


def write_record(record: Path, paks: Path, *relative: str) -> None:
    assets = [{"relative_path": path, "sha256": "x"} for path in relative]
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"paks": str(paks), "assets": assets}))


class RenamePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.record = Path(self.temporary.name) / "7.json"
        paks = Path(self.temporary.name) / "Paks"
        write_record(self.record, paks, "~mods/Fix_P.pak", "~mods/Fix_P.utoc")

    def test_stem_is_relative_to_paks(self) -> None:
        self.assertEqual(container_stem(self.record, "Fix_P"), "~mods/Fix_P")
        with self.assertRaisesRegex(ValueError, "expected one file stem"):
            container_stem(self.record, "Missing_P")

    def test_promotion_only_when_hidden(self) -> None:
        fix = ModContainer("Hero", "Fix_P", frozenset({"physics"}))
        main = ModContainer("Hero", "Outfit_P", frozenset({"physics"}))
        rename = promotion(self.record, fix, (main,))
        expected = ("~mods/Fix_P", "~mods/Fix_1_P", ("Outfit_P (Hero)",))
        assert rename is not None
        self.assertEqual((rename.old_stem, rename.new_stem, rename.wins), expected)
        self.assertIsNone(promotion(self.record, main, (fix,)))
        unrelated = ModContainer("X", "Zed_P", frozenset({"other"}))
        self.assertIsNone(promotion(self.record, fix, (unrelated,)))

    def test_default_renames_only_what_is_installed(self) -> None:
        self.assertEqual(default_renames(self.record), ())
        path = load_order_path(self.record)
        write_load_order(path, {"~mods/Main_P": "~mods/Main_1_P"})
        self.assertEqual(default_renames(self.record), ())
        write_load_order(path, {"~mods/Fix_0_P": "~mods/Fix_P"})
        back = ContainerRename(self.record, "~mods/Fix_P", "~mods/Fix_0_P")
        self.assertEqual(default_renames(self.record), (back,))


class LoadLastTuiTests(TuiFixture):
    def _install_rival(self) -> None:
        """Record Ayaka mod 2 as owning ~mods/Other_P.utoc, carrying the jacket."""
        (self.root / "store/ayaka/archives/stellar-blade/2").mkdir(parents=True)
        utoc = self.paks / "~mods/Other_P.utoc"
        utoc.parent.mkdir(parents=True, exist_ok=True)
        utoc.write_bytes(utoc_bytes((JACKET,)))
        record = self.root / "store/ayaka/state/stellar-blade/2/9.json"
        write_record(record, self.paks, "~mods/Other_P.utoc")

    async def _answer_dialog(self, app: OmaModsApp, pilot) -> str:
        for _ in range(40):
            await pilot.pause(0.05)
            if isinstance(app.screen, ConfirmDialog):
                break
        self.assertIsInstance(app.screen, ConfirmDialog)
        details = app.screen.details
        await pilot.press("y")
        await app.workers.wait_for_complete()
        await pilot.pause()
        return details

    def _alpha_files(self) -> list[str]:
        return sorted(path.name for path in self.paks.rglob("Alpha*"))

    async def test_load_last_then_default_then_uninstall(self) -> None:
        members = {
            "Black/Alpha_P.utoc": utoc_bytes((JACKET,)),
            "Black/Alpha_P.ucas": b"cas",
            "Black/Alpha_P.pak": directory_pak_bytes(()),
        }
        app = self._app(members)
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            self._install_rival()
            await pilot.press("i")
            await self._answer_dialog(app, pilot)
            await pilot.press("l")
            app.screen.query_one(WorkspaceStatus).refresh_state()  # Not on its timer.
            hints = app.screen.query_one(WorkspaceHints).current_hints
            self.assertIn("[b]P[/] load last", hints)
            await pilot.press("P")
            details = await self._answer_dialog(app, pilot)
            self.assertIn("Alpha_P.utoc -> ", details)
            self.assertIn("now loads over Other_P (Mod 2)", details)
            self.assertEqual(
                self._alpha_files(),
                ["Alpha_1_P.pak", "Alpha_1_P.ucas", "Alpha_1_P.utoc"],
            )
            inspector = app.screen.query_one("#mod-collisions", Static)
            self.assertIn("overrides Mod 2", str(inspector.render()))
            await pilot.press("u", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(self._alpha_files(), [])
            await pilot.press("i")
            details = await self._answer_dialog(app, pilot)
            self.assertIn("Alpha_1_P loads over Other_P", details)
            self.assertIn("Alpha_1_P.utoc", " ".join(self._alpha_files()))
            app.run_command_line(":load-default")
            await self._answer_dialog(app, pilot)
            self.assertEqual(
                self._alpha_files(), ["Alpha_P.pak", "Alpha_P.ucas", "Alpha_P.utoc"]
            )
            await pilot.press("u", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(self._alpha_files(), [])

    async def test_file_that_already_wins_is_left_alone(self) -> None:
        members = {
            "Black/Zed_P.utoc": utoc_bytes((JACKET,)),
            "Black/Zed_P.ucas": b"cas",
            "Black/Zed_P.pak": directory_pak_bytes(()),
        }
        app = self._app(members)
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            self._install_rival()
            await pilot.press("i")
            await self._answer_dialog(app, pilot)
            await pilot.press("P")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, ConfirmDialog)
            zed = sorted(path.name for path in self.paks.rglob("Zed*"))
            self.assertEqual(zed, ["Zed_P.pak", "Zed_P.ucas", "Zed_P.utoc"])


if __name__ == "__main__":
    unittest.main()
