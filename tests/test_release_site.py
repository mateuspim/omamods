"""Download, install, and update MGSVFix through the TUI service."""

from pathlib import Path
import tempfile
import unittest

from omamods.cdn_download import RetryPolicy
from omamods.download_queue import DownloadLog
from omamods.game_shelf import GameShelf
from omamods.mod_sites import RELEASE_SITE
from omamods.pak_games import PAK_OVERLAY_GAMES, PakOverlayGame
from omamods.nexus_config import UserSettings
from omamods.release_staging import pending_update
from omamods.tui.app import OmaModsApp
from omamods.tui.mods_screen import ModsScreen
from omamods.tui.service import ModsService, TuiHost
from tests.fakes import (
    FakeCommandRunner,
    FakeConfigFiles,
    FakeLauncher,
    FakeModArchives,
    FakeNexusTransport,
    FakeReleaseTransport,
    FakeShelfScanner,
    FakeSleep,
    codeberg_release,
)

MGSV = PAK_OVERLAY_GAMES["metalgearsolidvtpp"]
MGSVFIX_LATEST = "https://codeberg.org/api/v1/repos/Lyall/MGSVFix/releases/latest"
MGSVFIX_FILES = {"MGSVFix.asi": b"asi", "MGSVFix.ini": b"[ini]", "winmm.dll": b"ld"}


class FakeMgsvFolder:
    """Point MGSV at one temporary game folder."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def __call__(self, game: PakOverlayGame, settings: UserSettings) -> Path:
        return self.root


class FakeMgsvLaunchOptions:
    """Return MGSV's Steam launch options."""

    def __init__(self, options: str) -> None:
        self.options = options

    def __call__(self, app_id: str) -> tuple[str, ...]:
        return (self.options,)


class ReleaseFixture(unittest.IsolatedAsyncioTestCase):
    """A service whose MGSV folder and forge are fakes; holds no tests."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.game_root = base / "MGS_TPP"
        self.game_root.mkdir()
        self.forge = FakeReleaseTransport(codeberg_release())
        self.nexus = FakeNexusTransport()
        self.options = FakeMgsvLaunchOptions("%command%")
        host = TuiHost(
            base / "config.toml",
            base / "store",
            {},
            FakeConfigFiles(),
            self.nexus,
            FakeModArchives({1: MGSVFIX_FILES}),
            FakeCommandRunner(),
            FakeLauncher(),
            FakeMgsvFolder(self.game_root),
            Path("/bin/omamods"),
            base / "applications",
            FakeShelfScanner(GameShelf((), (), ())),
            retry=RetryPolicy(sleep=FakeSleep()),
            read_launch_options=self.options,
            release_transport=self.forge,
        )
        self.service = ModsService(host)

    def _mgsvfix(self):
        return self.service.staged_mod(MGSV, 1, RELEASE_SITE)


class ReleaseSiteTests(ReleaseFixture):
    def test_mgsvfix_is_listed_before_any_download(self) -> None:
        (mod,) = self.service.staged_mods(MGSV)
        self.assertEqual((mod.site, mod.title), (RELEASE_SITE, "MGSVFix"))
        self.assertEqual(
            self.service.mod_page_url(MGSV, 1, RELEASE_SITE),
            "https://codeberg.org/Lyall/MGSVFix",
        )

    def test_download_and_install_put_files_beside_the_exe(self) -> None:
        (path,) = self.service.release.download(MGSV, 1)
        self.assertEqual(path.name, "MGSVFix_0.0.3.zip")
        self.assertEqual(self.service.release.download(MGSV, 1), ())
        count = self.service.install(MGSV, 1, 9001, None, RELEASE_SITE)
        self.assertEqual(count, 3)
        self.assertEqual((self.game_root / "winmm.dll").read_bytes(), b"ld")
        self.assertEqual(self._mgsvfix().installed, frozenset({9001}))
        self.assertEqual(self.nexus.requests, [])  # Nexus never sees this.

    def test_install_brings_the_winmm_launch_warning(self) -> None:
        self.assertFalse(self.service.requirements.launch_advice(MGSV).needed)
        self.service.release.download(MGSV, 1)
        self.service.install(MGSV, 1, 9001, None, RELEASE_SITE)
        advice = self.service.requirements.launch_advice(MGSV)
        self.assertEqual(advice.missing, ("winmm",))
        self.assertEqual(advice.loader, "ASI loader")
        self.options.options = 'WINEDLLOVERRIDES="winmm=n,b" %command%'
        self.assertFalse(self.service.requirements.launch_advice(MGSV).needed)

    def test_uninstall_leaves_the_game_folder_as_it_was(self) -> None:
        self.service.release.download(MGSV, 1)
        self.service.install(MGSV, 1, 9001, None, RELEASE_SITE)
        self.assertEqual(self.service.revert(MGSV, 1, 9001, RELEASE_SITE), 3)
        self.assertEqual(list(self.game_root.iterdir()), [])

    def test_a_newer_release_is_reported_as_an_update(self) -> None:
        self.service.release.download(MGSV, 1)
        self.service.install(MGSV, 1, 9001, None, RELEASE_SITE)
        self.forge.reply = codeberg_release("0.0.4", 9100, "MGSVFix_0.0.4.zip")
        mod = self.service.release.refresh(MGSV, 1)
        self.assertEqual(pending_update(mod).file_name, "MGSVFix_0.0.4.zip")

    def test_retry_downloads_a_failed_queue_entry_again(self) -> None:
        self.service.release.download(MGSV, 1)
        log = DownloadLog(Path(self.temporary.name) / "store/downloads")
        (status,) = log.statuses()
        self.assertEqual(status.site, RELEASE_SITE)
        self._mgsvfix().archives[9001].unlink()
        self.assertTrue(self.service.retry(status))
        self.assertEqual(len(self.forge.downloads), 2)

    def test_retry_of_an_older_release_says_why_it_cannot(self) -> None:
        self.service.release.download(MGSV, 1)
        self.forge.reply = codeberg_release("0.0.4", 9100, "MGSVFix_0.0.4.zip")
        with self.assertRaisesRegex(ValueError, "older releases"):
            self.service.release.retry(MGSV, 1, 9001)


class ReleaseScreenTests(ReleaseFixture):
    async def _open_mods(self, app: OmaModsApp, pilot) -> None:
        await app.workers.wait_for_complete()
        app.push_screen(ModsScreen(self.service, MGSV))
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

    async def test_d_then_i_installs_mgsvfix(self) -> None:
        app = OmaModsApp(self.service)
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_mods(app, pilot)
            # Opening the screen already asked Codeberg for the newest release.
            self.assertEqual(self.forge.requests[:1], [MGSVFIX_LATEST])
            await pilot.press("d")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("i", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual((self.game_root / "MGSVFix.asi").read_bytes(), b"asi")

    async def test_opening_offline_still_lists_mgsvfix(self) -> None:
        self.forge.reply = OSError("offline")
        app = OmaModsApp(self.service)
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_mods(app, pilot)
            screen = app.screen
            self.assertIsInstance(screen, ModsScreen)
            self.assertEqual([m.title for m in screen.mods], ["MGSVFix"])


if __name__ == "__main__":
    unittest.main()
