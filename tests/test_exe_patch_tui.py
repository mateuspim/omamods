"""The games screen applies and restores built-in exe patches."""

from dataclasses import replace
from io import StringIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from rich.console import Console
from textual.widgets import Input

from omamods.game_shelf import MOD_READY, GameShelf, ShelfEntry, build_shelf
from omamods.installed_games import InstalledGame, InstalledScan
from omamods.manifests import GameManifest
from omamods.pak_games import PakGameCatalog
from omamods.tui.dialogs import ConfirmDialog, TextPrompt
from omamods.tui.exe_patch_site import ExePatchSite
from omamods.tui.shelf_view import entry_detail
from tests.fakes import FakeShelfScanner
from tests.test_patch_cli import FAKE_GAME
from tests.test_tui import TuiFixture

MGR = GameManifest(
    "metalgearrising",
    "METAL GEAR RISING: REVENGEANCE",
    "discovery",
    ("steam",),
    "exe-patcher",
    (),
    235460,
)


def _render(entry: ShelfEntry) -> str:
    console = Console(file=StringIO(), width=200)
    console.print(entry_detail(entry, None))
    output = console.file
    assert isinstance(output, StringIO)
    return output.getvalue()


def patch_shelf(root: Path) -> GameShelf:
    """METAL GEAR RISING installed under root, using the fake patch build."""
    game = InstalledGame("Steam", "235460", "MGR", root / "MGR", True)
    shelf = build_shelf((MGR,), PakGameCatalog(), InstalledScan((game,), ()), (root,))
    entries = tuple(replace(e, exe_patch=FAKE_GAME) for e in shelf.entries)
    return replace(shelf, entries=entries)


class ShelfMarkingTests(unittest.TestCase):
    def test_exe_patch_games_are_mod_ready(self) -> None:
        shelf = build_shelf((MGR,), PakGameCatalog(), InstalledScan((), ()), ())
        entry = shelf.entries[0]
        self.assertEqual(entry.section, MOD_READY)
        self.assertIsNotNone(entry.exe_patch)
        self.assertIsNone(entry.pak_game)
        self.assertIn("built-in ultrawide exe patch", _render(entry))


class ExePatchSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "MGR").mkdir()
        self.exe = self.root / "MGR" / "Game.exe"
        self.exe.write_bytes(b"original")
        settings = SimpleNamespace(storage_root=self.root / "store")
        self.site = ExePatchSite(SimpleNamespace(settings=settings))  # type: ignore[arg-type]
        self.entry = patch_shelf(self.root).entries[0]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_apply_then_revert(self) -> None:
        self.assertFalse(self.site.is_patched(self.entry))
        self.assertIn("patched for x", self.site.apply(self.entry, "x"))
        self.assertEqual(self.exe.read_bytes(), b"ORIGINALx")
        self.assertTrue(self.site.is_patched(self.entry))
        self.assertIn("restored", self.site.revert(self.entry))
        self.assertEqual(self.exe.read_bytes(), b"original")

    def test_missing_exe_and_non_patch_games(self) -> None:
        self.exe.unlink()
        with self.assertRaisesRegex(ValueError, "expected an installed Game.exe"):
            self.site.state(self.entry)
        with self.assertRaisesRegex(ValueError, "built-in exe patch"):
            self.site.revert(replace(self.entry, exe_patch=None))


class ExePatchScreenTests(TuiFixture):
    async def test_enter_patches_then_restores(self) -> None:
        (self.root / "MGR").mkdir()
        exe = self.root / "MGR" / "Game.exe"
        exe.write_bytes(b"original")
        self.scanner = FakeShelfScanner(patch_shelf(self.root))
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, TextPrompt)
            app.screen.query_one(Input).value = "x"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(exe.read_bytes(), b"ORIGINALx")
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, ConfirmDialog)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(exe.read_bytes(), b"original")
            messages = [str(n.message) for n in app._notifications]
            self.assertIn("Pick 1080p.", messages)


if __name__ == "__main__":
    unittest.main()
