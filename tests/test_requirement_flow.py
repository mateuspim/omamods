"""Install a Cyberpunk mod with its requirements through the TUI service."""

from io import StringIO
from pathlib import Path
import tempfile
import unittest

from omamods.cdn_download import RetryPolicy
from omamods.game_shelf import GameShelf
from omamods.nexus_api import NexusFile
from omamods.nexus_config import UserSettings
from omamods.pak_games import PAK_OVERLAY_GAMES, PakOverlayGame
from omamods.tui.app import OmaModsApp
from rich.console import Console
from omamods.tui.launch_options_dialog import LaunchOptionsDialog
from omamods.tui.mods_screen import ModsScreen
from omamods.tui.requirement_flow import newest_main_file
from omamods.tui.requirements_dialog import (
    RequirementsDialog,
    file_size,
    requirement_notes,
    requirement_table,
)
from omamods.tui.service import ModsService, TuiHost
from tests.fakes import (
    FakeCommandRunner,
    FakeConfigFiles,
    FakeLauncher,
    FakeModArchives,
    FakeNexusSite,
    FakeShelfScanner,
    FakeSleep,
)

CYBERPUNK = PAK_OVERLAY_GAMES["cyberpunk-2077"]
TARGET = 100
MAIN = NexusFile(7, "Black.zip", "MAIN", 1)
MEMBERS = {
    TARGET: {"archive/pc/mod/tp.archive": b"tp"},
    4198: {"red4ext/plugins/ArchiveXL/ArchiveXL.dll": b"axl"},
    2380: {"red4ext/RED4ext.dll": b"r4", "bin/x64/winmm.dll": b"proxy"},
}


class FakeGameRoot:
    """Point every game at one temporary game folder."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def __call__(self, game: PakOverlayGame, settings: UserSettings) -> Path:
        return self.root


class FakeLaunchOptions:
    """Return fixed Steam launch options and record which app was asked for."""

    def __init__(self, options: tuple[str, ...] = ()) -> None:
        self.options = options
        self.asked: list[str] = []

    def __call__(self, app_id: str) -> tuple[str, ...]:
        self.asked.append(app_id)
        return self.options


def rendered(plan) -> str:
    console = Console(width=160, record=True, file=StringIO())
    console.print(requirement_table(plan))
    return console.export_text()


class FlowFixture(unittest.IsolatedAsyncioTestCase):
    """Fakes shared by the flow tests; holds no tests of its own."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.game_root = base / "Cyberpunk 2077"
        (self.game_root / "bin/x64").mkdir(parents=True)
        self.site = FakeNexusSite()
        self.site.requirement_graph = {TARGET: (4198,), 4198: (2380,)}
        self.launcher = FakeLauncher()
        self.options = FakeLaunchOptions(('WINEDLLOVERRIDES="winmm=n,b" %command%',))
        config_files = FakeConfigFiles()
        config_files.contents[base / "config.toml"] = '[nexus]\napi_key = "k"\n'
        self.host = TuiHost(
            base / "config.toml",
            base / "store",
            {},
            config_files,
            self.site,
            FakeModArchives(MEMBERS),
            FakeCommandRunner(),
            self.launcher,
            FakeGameRoot(self.game_root),
            Path("/bin/omamods"),
            base / "applications",
            FakeShelfScanner(GameShelf((), (), ())),
            None,
            RetryPolicy(sleep=FakeSleep()),
            self.options,
        )
        self.service = ModsService(self.host)
        url = self.service.mod_page_url(CYBERPUNK, TARGET)
        self.service.fetch_mod(CYBERPUNK, url)
        self.service.download(CYBERPUNK, TARGET, MAIN)

    def _plan(self):
        mod = self.service.staged_mod(CYBERPUNK, TARGET)
        return self.service.requirements.plan(CYBERPUNK, mod, (MAIN,))


class PlanTests(FlowFixture):
    def test_plan_lists_missing_requirements_in_order(self) -> None:
        plan = self._plan()
        self.assertEqual([s.mod_id for s in plan.steps], [2380, 4198])
        self.assertEqual([f.file_id for f in plan.target.files], [MAIN.file_id])
        self.assertTrue(plan.needs_work)
        text = rendered(plan)
        self.assertIn("Mod 2380", text)
        self.assertIn("Sample Outfit (this mod)", text)
        self.assertIn("one at a time", requirement_notes(plan))
        self.assertEqual(self.options.asked, ["1091500"])

    def test_frameworks_on_disk_count_as_installed(self) -> None:
        (self.game_root / "red4ext").mkdir()
        (self.game_root / "red4ext/RED4ext.dll").write_bytes(b"by hand")
        plan = self._plan()
        self.assertEqual([s.mod_id for s in plan.steps], [4198])
        self.assertEqual(plan.present, ("Mod 2380",))

    def test_missing_overrides_are_explained(self) -> None:
        self.options.options = ("PROTON_ENABLE_HDR=1 %command%",)
        plan = self._plan()
        self.assertEqual(plan.missing_dlls, ("winmm",))
        self.assertIn('WINEDLLOVERRIDES="winmm=n,b"', requirement_notes(plan))

    def test_small_files_show_kilobytes(self) -> None:
        # Native Settings UI (40 KB) used to show as "0.0 MB".
        self.assertEqual([file_size(k) for k in (0, 40, 2048)], ["", "40 KB", "2.0 MB"])

    def test_newest_main_file_wins(self) -> None:
        files = (
            NexusFile(1, "old.zip", "MAIN", 10),
            NexusFile(2, "new.zip", "MAIN", 20),
            NexusFile(3, "opt.zip", "OPTIONAL", 30),
        )
        self.assertEqual(newest_main_file(files).file_id, 2)
        self.assertIsNone(newest_main_file(files[2:]))


class ChainTests(FlowFixture):
    def test_premium_installs_requirements_then_the_mod(self) -> None:
        flow = self.service.requirements
        flow.start(self._plan())
        self.assertTrue(flow.running)
        messages = flow.advance()
        self.assertEqual(messages[-1], "Sample Outfit: it and its requirements are in")
        self.assertEqual((self.game_root / "bin/x64/winmm.dll").read_bytes(), b"proxy")
        self.assertTrue((self.game_root / "archive/pc/mod/tp.archive").is_file())
        self.assertFalse(flow.running)

    def test_browser_downloads_open_one_window_at_a_time(self) -> None:
        self.site.premium = False
        flow = self.service.requirements
        flow.start(self._plan())
        self.assertEqual(flow.advance(), ("Mod 2380: waiting for its download",))
        opened = [c[-1] for c in self.launcher.launched]
        self.assertEqual(len(opened), 1)
        self.assertIn("/mods/2380?tab=files&file_id=7", opened[0])
        # The click arrives through the nxm handler; stage it the Premium way.
        self.site.premium = True
        self.service.download(CYBERPUNK, 2380, MAIN)
        self.site.premium = False
        self.assertEqual(
            flow.advance(),
            ("Mod 2380: installed 2 files", "Mod 4198: waiting for its download"),
        )

    def test_a_second_chain_waits_for_the_first(self) -> None:
        self.site.premium = False
        flow = self.service.requirements
        plan = self._plan()
        flow.start(plan)
        with self.assertRaisesRegex(ValueError, "expected it to finish"):
            flow.start(plan)


class RestartTests(FlowFixture):
    def _restart(self) -> ModsService:
        return ModsService(self.host)

    def test_chain_survives_a_restart(self) -> None:
        # Regression: a TUI restart dropped the chain after RED4ext installed,
        # leaving ArchiveXL staged but never installed.
        self.site.premium = False
        self.service.requirements.start(self._plan())
        self.service.requirements.advance()
        self.site.premium = True
        self.service.download(CYBERPUNK, 2380, MAIN)
        resumed = self._restart().requirements
        self.assertEqual(resumed.target_name, "Sample Outfit")
        messages = resumed.advance()
        self.assertEqual(messages[0], "Mod 2380: installed 2 files")
        self.assertEqual(messages[-1], "Sample Outfit: it and its requirements are in")
        self.assertFalse(resumed.record.exists())

    def test_waiting_download_reopens_after_restart(self) -> None:
        self.site.premium = False
        self.service.requirements.start(self._plan())
        self.service.requirements.advance()
        self.launcher.launched.clear()
        resumed = self._restart().requirements
        self.assertEqual(resumed.advance(), ("Mod 2380: waiting for its download",))
        self.assertEqual(len(self.launcher.launched), 1)

    def test_failed_chain_is_forgotten(self) -> None:
        MEMBERS[4198]["mods/Bad/info.json"] = b"{}"
        self.addCleanup(MEMBERS[4198].pop, "mods/Bad/info.json")
        flow = self.service.requirements
        flow.start(self._plan())
        with self.assertRaisesRegex(ValueError, "REDmod"):
            flow.advance()
        self.assertFalse(flow.record.exists())
        self.assertIsNone(self._restart().requirements.target_name)

    def test_unreadable_record_is_reported_once(self) -> None:
        record = self.service.requirements.record
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text("{")
        flow = self._restart().requirements
        self.assertTrue(flow.has_work)
        with self.assertRaisesRegex(ValueError, "Could not resume"):
            flow.advance()
        self.assertFalse(flow.has_work)
        self.assertFalse(record.exists())

    def test_plan_marks_downloaded_steps(self) -> None:
        self.service.download(CYBERPUNK, 4198, MAIN)
        plan = self._plan()
        self.assertEqual(plan.staged, frozenset({4198, TARGET}))
        text = rendered(plan)
        self.assertEqual(text.count("downloaded"), 2)
        self.assertEqual(text.count("to download"), 1)


class ScreenTests(FlowFixture):
    async def _press_install(
        self, app: OmaModsApp, pilot, presses: int, keys: tuple[str, ...] = ("i",)
    ) -> None:
        await app.workers.wait_for_complete()
        app.push_screen(ModsScreen(self.service, CYBERPUNK))
        await pilot.pause()
        for _ in range(presses):
            await pilot.press(*keys)
        # The worker waits on the dialog, so wait for the dialog instead.
        for _ in range(50):
            if isinstance(app.screen, RequirementsDialog):
                break
            await pilot.pause(0.05)

    def _dialogs(self, app: OmaModsApp) -> int:
        return sum(isinstance(s, RequirementsDialog) for s in app.screen_stack)

    async def test_install_key_shows_the_plan_and_runs_it(self) -> None:
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._press_install(app, pilot, 1)
            self.assertIsInstance(app.screen, RequirementsDialog)
            await pilot.press("y")
            await pilot.pause()
            self.assertTrue(self.service.requirements.running)
            app.tick_requirements()
            await app.workers.wait_for_complete()
            self.assertTrue((self.game_root / "red4ext/RED4ext.dll").is_file())

    async def test_repeated_presses_open_one_dialog(self) -> None:
        # Regression: each i press used to start its own check and dialog.
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._press_install(app, pilot, 3)
            await pilot.press("i", "i")
            await pilot.pause(0.2)
            self.assertEqual(self._dialogs(app), 1)
            self.assertEqual(len(self.site.queries), 3)  # One tree: 3 levels.

    async def test_enter_on_a_staged_file_checks_requirements_too(self) -> None:
        # Regression: Enter installed the mod while its requirements were missing.
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._press_install(app, pilot, 1, ("l", "enter"))
            self.assertIsInstance(app.screen, RequirementsDialog)
            self.assertFalse((self.game_root / "archive/pc/mod/tp.archive").exists())

    async def test_install_key_waits_for_a_running_chain(self) -> None:
        self.site.premium = False
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._press_install(app, pilot, 1)
            await pilot.press("y")
            await pilot.pause()
            queries = len(self.site.queries)
            await pilot.press("i")
            await pilot.pause(0.2)
            self.assertEqual(len(self.site.queries), queries)
            self.assertEqual(self._dialogs(app), 0)


class LaunchOptionsTests(FlowFixture):
    def setUp(self) -> None:
        super().setUp()
        self.options.options = ("PROTON_ENABLE_HDR=1 %command%",)
        (self.game_root / "red4ext").mkdir()
        (self.game_root / "red4ext/RED4ext.dll").write_bytes(b"r4")

    async def _open_mods(self, app: OmaModsApp, pilot) -> None:
        await app.workers.wait_for_complete()
        app.push_screen(ModsScreen(self.service, CYBERPUNK))
        await pilot.pause()
        await app.workers.wait_for_complete()

    def test_flow_advice_merges_into_steam_line(self) -> None:
        advice = self.service.requirements.launch_advice(CYBERPUNK)
        self.assertEqual(
            advice.suggested,
            'WINEDLLOVERRIDES="winmm=n,b" PROTON_ENABLE_HDR=1 %command%',
        )

    def test_plan_notes_show_the_line_to_paste(self) -> None:
        notes = requirement_notes(self._plan())
        self.assertIn("Steam has now:", notes)
        self.assertIn('WINEDLLOVERRIDES="winmm=n,b" PROTON_ENABLE_HDR=1', notes)

    async def test_opening_mods_warns_and_l_copies_the_line(self) -> None:
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._open_mods(app, pilot)
            warnings = [n.message for n in app._notifications]
            self.assertTrue(any("press L" in m for m in warnings))
            await pilot.press("L")
            await pilot.pause()
            self.assertIsInstance(app.screen, LaunchOptionsDialog)
            await pilot.press("c")
            await pilot.pause()
            line = 'WINEDLLOVERRIDES="winmm=n,b" PROTON_ENABLE_HDR=1 %command%'
            self.assertIn(("wl-copy", "--", line), self.launcher.launched)
            self.assertEqual(app.clipboard, line)

    async def test_fixed_steam_line_shows_no_warning(self) -> None:
        self.options.options = ('WINEDLLOVERRIDES="winmm=n,b" %command%',)
        app = OmaModsApp(self.service)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._open_mods(app, pilot)
            warnings = [n.message for n in app._notifications]
            self.assertFalse(any("press L" in m for m in warnings))


if __name__ == "__main__":
    unittest.main()
