"""Grow and shrink the mods screen's downloads panel."""

from pathlib import Path
import tempfile
import time
import unittest

from textual.widgets import DataTable, Input, Static

from omamods.cdn_download import RetryPolicy
from omamods.download_queue import DownloadStatus
from omamods.game_shelf import GameShelf
from omamods.mod_fetch import download_log
from omamods.nexus_config import UserSettings
from omamods.pak_games import PAK_OVERLAY_GAMES, PakOverlayGame
from omamods.tui.app import OmaModsApp
from omamods.tui.downloads_panel import (
    FULL_QUEUE,
    GAME_QUEUE,
    MINIMIZED,
    DownloadsPanel,
    next_panel_mode,
    panel_statuses,
    panel_title,
)
from omamods.tui.downloads_screen import DownloadsScreen
from omamods.tui.mods_screen import ModsScreen
from omamods.tui.service import ModsService, TuiHost
from tests.fakes import (
    FakeArchiveReader,
    FakeCommandRunner,
    FakeConfigFiles,
    FakeLauncher,
    FakeNexusSite,
    FakeShelfScanner,
    FakeSleep,
)

CYBERPUNK = PAK_OVERLAY_GAMES["cyberpunk-2077"]


def entry(game: str, mod: int, state: str) -> DownloadStatus:
    now = time.time()
    return DownloadStatus(
        game, mod, 7, f"{game}-{mod}.zip", state, 50, 100, 1024.0, now, now, now
    )


class FakeGameFolder:
    """Point every game at one temporary folder."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def __call__(self, game: PakOverlayGame, settings: UserSettings) -> Path:
        return self.folder


class PanelModeTests(unittest.TestCase):
    def test_modes_cycle_and_wrap(self) -> None:
        self.assertEqual(next_panel_mode(MINIMIZED), GAME_QUEUE)
        self.assertEqual(next_panel_mode(GAME_QUEUE), FULL_QUEUE)
        self.assertEqual(next_panel_mode(FULL_QUEUE), MINIMIZED)
        with self.assertRaisesRegex(ValueError, "mode='huge'"):
            next_panel_mode("huge")

    def test_rows_follow_the_mode(self) -> None:
        statuses = (entry("cyberpunk-2077", 1, "done"), entry("cronos", 2, "done"))
        self.assertEqual(panel_statuses(statuses, MINIMIZED, "cronos"), ())
        self.assertEqual(panel_statuses(statuses, GAME_QUEUE, "cronos"), statuses[1:])
        self.assertEqual(panel_statuses(statuses, FULL_QUEUE, "cronos"), statuses)

    def test_title_names_the_next_step(self) -> None:
        self.assertIn("D: this game's queue", panel_title(MINIMIZED, "Cronos"))
        self.assertIn("Cronos · D: all games", panel_title(GAME_QUEUE, "Cronos"))
        self.assertIn("D: minimize", panel_title(FULL_QUEUE, "Cronos"))


class PanelScreenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        files = FakeConfigFiles()
        files.contents[base / "config.toml"] = '[nexus]\napi_key = "k"\n'
        host = TuiHost(
            base / "config.toml",
            base / "store",
            {},
            files,
            FakeNexusSite(),
            FakeArchiveReader({}),
            FakeCommandRunner(),
            FakeLauncher(),
            FakeGameFolder(base / "game"),
            Path("/bin/omamods"),
            base / "applications",
            FakeShelfScanner(GameShelf((), (), ())),
            None,
            RetryPolicy(sleep=FakeSleep()),
        )
        self.service = ModsService(host)
        self.log = download_log(base / "store")
        self.log.write(entry("cyberpunk-2077", 4198, "downloading"))
        self.log.write(entry("cronos", 38, "failed"))

    async def _open(self, app: OmaModsApp, pilot) -> DownloadsPanel:
        await app.workers.wait_for_complete()
        app.push_screen(ModsScreen(self.service, CYBERPUNK))
        await pilot.pause()
        return app.screen.query_one(DownloadsPanel)

    def _bar(self, panel: DownloadsPanel) -> str:
        return str(panel.query_one("#downloads-bar", Static).render())

    def _rows(self, panel: DownloadsPanel) -> list[str]:
        table = panel.query_one("#downloads-table", DataTable)
        return [str(table.get_row_at(i)[2]) for i in range(table.row_count)]

    async def test_starts_minimized_with_a_summary_bar(self) -> None:
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            panel = await self._open(app, pilot)
            self.assertEqual(panel.mode, MINIMIZED)
            self.assertIn("1 downloading (Mod 4198 50%", self._bar(panel))
            self.assertIn("1 failed", self._bar(panel))
            self.assertFalse(panel.query_one("#downloads-table").display)

    async def test_d_cycles_game_full_and_back(self) -> None:
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            panel = await self._open(app, pilot)
            await pilot.press("D")
            self.assertEqual(panel.mode, GAME_QUEUE)
            self.assertEqual(self._rows(panel), ["cyberpunk-2077-4198.zip"])
            self.assertTrue(app.screen.query_one("#mods-body").display)
            await pilot.press("D")
            self.assertEqual(panel.mode, FULL_QUEUE)
            self.assertEqual(len(self._rows(panel)), 2)
            self.assertFalse(app.screen.query_one("#mods-body").display)
            await pilot.press("D")
            self.assertEqual(panel.mode, MINIMIZED)
            self.assertTrue(app.screen.query_one("#mods-body").display)
            self.assertNotIsInstance(app.screen, DownloadsScreen)

    async def test_refresh_picks_up_new_downloads(self) -> None:
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            panel = await self._open(app, pilot)
            await pilot.press("D")
            self.log.write(entry("cyberpunk-2077", 107, "waiting for browser"))
            panel.refresh_queue()
            self.assertEqual(len(self._rows(panel)), 2)
            self.assertIn("1 waiting for browser", self._bar(panel))

    async def test_dl_command_sets_a_size_and_clear_works(self) -> None:
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            panel = await self._open(app, pilot)
            await pilot.press("colon")
            app.screen.query_one(Input).value = "dl full"
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(panel.mode, FULL_QUEUE)
            await pilot.press("c")  # The table has focus in full mode.
            await pilot.pause()
            self.assertEqual(self._rows(panel), ["cyberpunk-2077-4198.zip"])

    async def test_x_removes_the_selected_entry(self) -> None:
        self.log.write(entry("cronos", 39, "waiting for browser"))
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            panel = await self._open(app, pilot)
            panel.set_mode(FULL_QUEUE)
            panel.query_one("#downloads-table", DataTable).focus()
            await pilot.pause()
            await pilot.press("x")  # The newest entry is selected first.
            await pilot.pause()
            self.assertNotIn("cronos-39.zip", self._rows(panel))
            self.assertEqual(len(self._rows(panel)), 2)

    async def test_capital_c_clears_all_but_active(self) -> None:
        self.log.write(entry("cronos", 39, "waiting for browser"))
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            panel = await self._open(app, pilot)
            panel.set_mode(FULL_QUEUE)
            panel.query_one("#downloads-table", DataTable).focus()
            await pilot.press("C")
            await pilot.pause()
            self.assertEqual(self._rows(panel), ["cyberpunk-2077-4198.zip"])

    async def test_queue_command_still_opens_the_queue_screen(self) -> None:
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._open(app, pilot)
            await pilot.press("colon")
            app.screen.query_one(Input).value = "queue"
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, DownloadsScreen)


if __name__ == "__main__":
    unittest.main()
