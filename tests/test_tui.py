"""Drive the TUI headlessly against fake Nexus, archives, and host programs."""

from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image as PilImage
from textual.widgets import DataTable, Input, OptionList

from omamods.cdn_download import RetryPolicy
from omamods.nexus_config import UserSettings
from omamods.pak_games import PakOverlayGame
from omamods.tui.app import OmaModsApp
from omamods.tui.dialogs import ConfirmDialog, InfoDialog
from omamods.tui.mods_screen import ModsScreen
from omamods.tui.downloads_screen import DownloadsScreen
from omamods.tui.service import ModsService, TuiHost
from tests.fakes import (
    FakeArchiveReader,
    FakeCommandRunner,
    FakeConfigFiles,
    FakeSleep,
    FakeHyprland,
    FakeLauncher,
    FakeNexusSite,
)

URL = "https://www.nexusmods.com/stellarblade/mods/1"


def png_bytes() -> bytes:
    stream = BytesIO()
    PilImage.new("RGB", (4, 4), "purple").save(stream, "PNG")
    return stream.getvalue()


class FakePaksLocator:
    """Point every game at one temporary Paks folder."""

    def __init__(self, paks: Path) -> None:
        self.paks = paks

    def __call__(self, game: PakOverlayGame, settings: UserSettings) -> Path:
        return self.paks


class TuiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paks = self.root / "SB/Content/Paks"
        self.paks.mkdir(parents=True)
        self.config_files = FakeConfigFiles()
        self.config = self.root / "config.toml"
        self.config_files.contents[self.config] = '[nexus]\napi_key = "k"\n'
        self.site = FakeNexusSite()
        self.site.picture = png_bytes()
        self.launcher = FakeLauncher()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _app(
        self, members: dict[str, bytes], hyprland: FakeHyprland | None = None
    ) -> OmaModsApp:
        host = TuiHost(
            self.config,
            self.root / "store",
            {},
            self.config_files,
            self.site,
            FakeArchiveReader(members),
            hyprland or FakeCommandRunner(),
            self.launcher,
            FakePaksLocator(self.paks),
            Path("/bin/omamods"),
            self.root / "applications",
            "brave" if hyprland else None,
            RetryPolicy(sleep=FakeSleep()),
        )
        return OmaModsApp(ModsService(host))

    async def _open_stellar_blade_and_add(self, app: OmaModsApp, pilot) -> None:
        await pilot.press("down", "enter", "a")
        app.screen.query_one(Input).value = URL
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

    async def test_add_download_and_install(self) -> None:
        app = self._app({"Black/s.pak": b"pak"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            staged = self.root / "store/archives/stellar-blade/1/7/Black.zip"
            self.assertTrue(staged.is_file())
            self.assertEqual(app.screen.query_one("#files", DataTable).row_count, 2)
            await pilot.press("i", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual((self.paks / "~mods/Black/s.pak").read_bytes(), b"pak")
            await pilot.press("o")
            self.assertEqual(self.launcher.launched[-1][0], "imv")

    async def test_variant_choice_installs_one_folder(self) -> None:
        app = self._app({"Mod/Black/s.pak": b"b", "Mod/White/s.pak": b"w"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await pilot.press("i", "down", "enter", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertTrue((self.paks / "~mods/White/s.pak").is_file())
            self.assertFalse((self.paks / "~mods/Black").exists())

    async def test_non_premium_opens_files_tab(self) -> None:
        self.site.premium = False
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            command, url = self.launcher.launched[-1]
            self.assertEqual(command, "xdg-open")
            self.assertIn("tab=files&file_id=7", url)

    async def test_nexus_window_steps_through_each_file_then_closes(self) -> None:
        self.site.premium = False
        window = "brave-www.nexusmods.com__stellarblade_mods_1-Default"
        hyprland = FakeHyprland([{"address": "0xab", "initialClass": window}])
        app = self._app({}, hyprland)
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            opened = [c for c in self.launcher.launched if c[0] == "brave"]
            self.assertEqual(len(opened), 1)  # One window, showing file 7 first.
            self.assertIn("file_id=7", opened[0][1])
            staging = self.root / "store/archives/stellar-blade/1"
            for file_id, name in ((7, "Black.zip"), (8, "Hair.zip")):
                (staging / str(file_id)).mkdir(parents=True)
                (staging / str(file_id) / name).write_bytes(b"zip")
                app.advance_browser_downloads()
                await pilot.pause()
            opened = [c for c in self.launcher.launched if c[0] == "brave"]
            self.assertEqual(len(opened), 2)
            self.assertIn("file_id=8", opened[1][1])  # Jumped to the second file.
            self.assertEqual(len(hyprland.closed()), 2)  # After 7, and when done.

    async def test_unrequested_file_is_flagged_and_removable(self) -> None:
        self.site.premium = False
        app = self._app({}, FakeHyprland([]))
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            surprise = self.root / "store/archives/stellar-blade/1/99/Old.rar"
            surprise.parent.mkdir(parents=True)
            surprise.write_bytes(b"r")
            app.advance_browser_downloads()
            await pilot.pause()
            messages = [str(n.message) for n in app._notifications]
            self.assertTrue(
                any("did not ask for" in m and "Black 1.0" in m for m in messages)
            )
            app.screen.reload()
            await pilot.pause()
            table = app.screen.query_one("#files", DataTable)
            table.focus()
            table.move_cursor(row=table.row_count - 1)  # The surprise file.
            await pilot.press("x", "y")
            await pilot.pause()
            self.assertFalse(surprise.exists())

    async def test_installed_file_is_not_reinstalled(self) -> None:
        app = self._app({"Black/s.pak": b"pak"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await pilot.press("i", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("i")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, ConfirmDialog)
            self.assertTrue(
                any(
                    "Nothing new to install" in str(n.message)
                    for n in app._notifications
                )
            )

    async def test_install_mod_skips_optional_then_swap_by_toggling(self) -> None:
        app = self._app({"Black/s.pak": b"pak"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await pilot.press("i", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            store = self.root / "store/state/stellar-blade/1"
            self.assertEqual(sorted(p.name for p in store.iterdir()), ["7.json"])
            app.screen.query_one("#files", DataTable).focus()
            await pilot.press("enter", "y")  # Row 0: uninstall MAIN file 7.
            await pilot.pause()
            await pilot.press("down", "enter", "y")  # Row 1: install OPTIONAL 8.
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(sorted(p.name for p in store.iterdir()), ["8.json"])
            await pilot.press("u", "y")
            await pilot.pause()
            self.assertFalse((self.paks / "~mods/Black/s.pak").exists())

    async def test_download_queue_shows_failure_and_retries(self) -> None:
        self.site.fail_downloads = True
        app = self._app({})
        async with app.run_test(size=(160, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await pilot.press("D")
            await pilot.pause()
            self.assertIsInstance(app.screen, DownloadsScreen)
            queue = app.screen.query_one("#queue", DataTable)
            states = [queue.get_row_at(i)[0] for i in range(queue.row_count)]
            self.assertEqual(states, ["failed", "failed"])
            self.assertIn("HTTP 503", queue.get_row_at(0)[7])
            self.site.fail_downloads = False
            await pilot.press("r")
            await app.workers.wait_for_complete()
            app.screen.refresh_queue()
            self.assertEqual(queue.get_row_at(queue.cursor_row)[0], "done")
            await pilot.press("escape")
            self.assertNotIsInstance(app.screen, DownloadsScreen)

    async def _command(
        self, app: OmaModsApp, pilot, line: str, opens_dialog: bool = False
    ) -> None:
        await pilot.press("colon")
        app.screen.query_one(Input).value = line
        await pilot.press("enter")
        if not opens_dialog:  # A dialog's worker waits for our answer.
            await app.workers.wait_for_complete()
        await pilot.pause()

    async def test_vim_motions_and_game_command(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            games = app.screen.query_one("#games", OptionList)
            await pilot.press("j")
            self.assertEqual(games.highlighted, 1)
            await pilot.press("k")
            self.assertEqual(games.highlighted, 0)
            await pilot.press("G")
            self.assertEqual(games.highlighted, 1)
            await pilot.press("g", "g")
            self.assertEqual(games.highlighted, 0)
            await self._command(app, pilot, "game sb")
            self.assertIsInstance(app.screen, ModsScreen)
            self.assertEqual(app.screen.game.game_id, "stellar-blade")
            await self._command(app, pilot, "q")
            self.assertNotIsInstance(app.screen, ModsScreen)

    async def test_commands_install_by_name_and_report_errors(self) -> None:
        app = self._app({"Black/s.pak": b"pak"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await self._command(app, pilot, "inst Black", opens_dialog=True)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertTrue((self.paks / "~mods/Black/s.pak").is_file())
            await self._command(app, pilot, "bogus")
            messages = [str(n.message) for n in app._notifications]
            self.assertTrue(
                any("E492: Not an editor command: bogus" in m for m in messages)
            )
            await self._command(app, pilot, "help")
            self.assertIsInstance(app.screen, InfoDialog)
            await pilot.press("escape")

    async def test_h_and_l_switch_panes_in_one_press(self) -> None:
        # Regression: the focusable detail pane made each switch take two presses.
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            app.screen.query_one("#mods", OptionList).focus()
            await pilot.press("l")
            self.assertEqual(app.focused.id, "files")
            await pilot.press("h")
            self.assertEqual(app.focused.id, "mods")

    async def test_missing_picture_is_fetched_when_mod_is_shown(self) -> None:
        self.site.picture_online = False
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            screen = app.screen
            self.assertIsNone(screen.current.picture)
            self.site.picture_online = True
            screen.picture_attempts.clear()
            screen._show(screen.current)
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(screen.current.picture.name, "picture.png")

    async def test_slash_search_and_n(self) -> None:
        app = self._app({})
        for mod_id, name in ((2, "Hair Pack"), (3, "Blue Suit"), (4, "Hair Long")):
            archive = self.root / f"store/archives/stellar-blade/{mod_id}/0/{name}.zip"
            archive.parent.mkdir(parents=True)
            archive.write_bytes(b"z")
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("down", "enter")
            await pilot.pause()
            mods = app.screen.query_one("#mods", OptionList)
            await pilot.press("slash")
            app.screen.query_one(Input).value = "mod 4"
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(app.screen.mods[mods.highlighted].mod_id, 4)
            app.screen.search("mod")
            first = mods.highlighted
            await pilot.press("n")
            self.assertNotEqual(mods.highlighted, first)

    async def test_api_key_prompt_saves_key(self) -> None:
        self.config_files.contents.clear()
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("K")
            app.screen.query_one(Input).value = "newkey"
            await pilot.press("enter")
            await pilot.pause()
            self.assertIn('api_key = "newkey"', self.config_files.contents[self.config])


if __name__ == "__main__":
    unittest.main()
