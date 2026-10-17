"""Save MGSV's launch options to Steam from the mods screen (L, then w)."""

from pathlib import Path
import tempfile
import unittest

from omamods.cdn_download import RetryPolicy
from omamods.game_shelf import GameShelf
from omamods.nexus_config import UserSettings
from omamods.pak_games import PAK_OVERLAY_GAMES, PakOverlayGame
from omamods.steam_process import SteamProcess
from omamods.tui.app import OmaModsApp
from omamods.tui.dialogs import ConfirmDialog
from omamods.tui.launch_options_dialog import LaunchOptionsDialog
from omamods.tui.mods_screen import ModsScreen
from omamods.tui.service import ModsService, TuiHost
from tests.fakes import (
    FakeConfigFiles,
    FakeModArchives,
    FakeNexusTransport,
    FakeReleaseTransport,
    FakeShelfScanner,
    FakeSleep,
    FakeSteamClient,
    codeberg_release,
)

MGSV = PAK_OVERLAY_GAMES["metalgearsolidvtpp"]
LINE = 'WINEDLLOVERRIDES="winmm=n,b" %command%'


class FakeMgsvRoot:
    """Point MGSV at a temporary folder that already holds MGSVFix's loader."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def __call__(self, game: PakOverlayGame, settings: UserSettings) -> Path:
        return self.root


class FakeSteamConfig:
    """Hold one user's MGSV launch options; writing checks Steam is closed."""

    def __init__(self, client: FakeSteamClient, fail: bool = False) -> None:
        self.client = client
        self.fail = fail
        self.options = ""
        self.writes: list[tuple[str, str, Path]] = []

    def read(self, app_id: str) -> tuple[str, ...]:
        return (self.options,)

    def write(self, app_id: str, line: str, backups: Path) -> tuple[Path, ...]:
        if self.client.is_running:
            raise AssertionError("expected Steam closed before writing its config")
        if self.fail:
            raise ValueError("localconfig: expected app 287700 to be listed")
        self.writes.append((app_id, line, backups))
        self.options = line
        return (Path("/steam/userdata/1/config/localconfig.vdf"),)


class SteamSetupFixture(unittest.IsolatedAsyncioTestCase):
    """A service with MGSVFix's winmm.dll on disk and fake Steam; holds no tests."""

    def _service(self, running: bool, fail: bool = False) -> ModsService:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        (base / "MGS_TPP").mkdir()
        (base / "MGS_TPP/winmm.dll").write_bytes(b"loader")
        self.client = FakeSteamClient(running)
        self.config = FakeSteamConfig(self.client, fail)
        host = TuiHost(
            base / "config.toml",
            base / "store",
            {},
            FakeConfigFiles(),
            FakeNexusTransport(),
            FakeModArchives({}),
            self.client,
            self.client,
            FakeMgsvRoot(base / "MGS_TPP"),
            Path("/bin/omamods"),
            base / "applications",
            FakeShelfScanner(GameShelf((), (), ())),
            retry=RetryPolicy(sleep=FakeSleep()),
            read_launch_options=self.config.read,
            release_transport=FakeReleaseTransport(codeberg_release()),
            write_launch_options=self.config.write,
            steam=SteamProcess(self.client, self.client, FakeSleep()),
        )
        return ModsService(host)


class SteamSetupServiceTests(SteamSetupFixture):
    def test_closed_steam_is_written_and_left_closed(self) -> None:
        service = self._service(running=False)
        message = service.steam_setup.save("287700", LINE)
        self.assertIn("Saved to Steam for 1 user", message)
        self.assertEqual(self.config.writes[0][:2], ("287700", LINE))
        self.assertEqual(self.client.launched, [])

    def test_running_steam_is_closed_then_restarted(self) -> None:
        service = self._service(running=True)
        service.steam_setup.save("287700", LINE)
        self.assertEqual(
            self.client.launched, [("steam", "-shutdown"), ("steam", "-silent")]
        )

    def test_a_failed_write_still_restarts_steam(self) -> None:
        service = self._service(running=True, fail=True)
        with self.assertRaisesRegex(ValueError, "287700"):
            service.steam_setup.save("287700", LINE)
        self.assertEqual(self.client.launched[-1], ("steam", "-silent"))


class SteamSetupScreenTests(SteamSetupFixture):
    async def _press_l_then_w(self, app: OmaModsApp, pilot) -> None:
        await app.workers.wait_for_complete()
        app.push_screen(ModsScreen(app.service, MGSV))
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.press("L")
        await pilot.pause()
        self.assertIsInstance(app.screen, LaunchOptionsDialog)
        await pilot.press("w")
        await pilot.pause()

    async def _finish(self, app: OmaModsApp, pilot) -> None:
        await app.workers.wait_for_complete()
        await pilot.pause()

    async def test_w_saves_at_once_when_steam_is_closed(self) -> None:
        app = OmaModsApp(self._service(running=False))
        async with app.run_test(size=(140, 45)) as pilot:
            await self._press_l_then_w(app, pilot)
            await self._finish(app, pilot)
            self.assertEqual(self.config.options, LINE)

    async def test_w_asks_before_closing_steam(self) -> None:
        app = OmaModsApp(self._service(running=True))
        async with app.run_test(size=(140, 45)) as pilot:
            await self._press_l_then_w(app, pilot)
            self.assertIsInstance(app.screen, ConfirmDialog)
            await pilot.press("y")
            await self._finish(app, pilot)
            self.assertEqual(self.config.options, LINE)
            self.assertEqual(self.client.launched[-1], ("steam", "-silent"))

    async def test_saying_no_leaves_steam_alone(self) -> None:
        app = OmaModsApp(self._service(running=True))
        async with app.run_test(size=(140, 45)) as pilot:
            await self._press_l_then_w(app, pilot)
            await pilot.press("n")
            await self._finish(app, pilot)
            self.assertEqual((self.config.options, self.client.launched), ("", []))


if __name__ == "__main__":
    unittest.main()
