"""Drive the TUI headlessly against fake Nexus, archives, and host programs."""

from dataclasses import replace
import json
from io import BytesIO, StringIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image as PilImage
from rich.console import Console
from textual.widgets import DataTable, Input, OptionList, Static

from omamods.cdn_download import RetryPolicy
from omamods.download_queue import DOWNLOADING, FAILED
from omamods.mod_fetch import download_log
from omamods.game_shelf import MOD_READY, GameShelf, ShelfEntry, build_shelf
from omamods.installed_games import InstalledGame, InstalledScan
from omamods.manifests import GameManifest
from omamods.nexus_config import UserSettings
from omamods.pak_games import PakGameCatalog, PakOverlayGame
from omamods.tui.app import OmaModsApp
from omamods.tui.dialogs import ConfirmDialog, InfoDialog
from omamods.tui.mod_rows import describe_mod
from omamods.tui.mods_screen import ModsScreen
from omamods.tui.preview import PicturePreview
from omamods.tui.downloads_screen import DownloadsScreen
from omamods.tui.games_screen import GamesScreen
from omamods.tui.service import ModsService, TuiHost
from tests.pak_builders import directory_pak_bytes, utoc_bytes
from tests.fakes import (
    FakeArchiveReader,
    FakeAyakaPages,
    FakeAyakaSession,
    FakeCommandRunner,
    FakeConfigFiles,
    FakeShelfScanner,
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


def manifest(game_id: str, name: str, app_id: int) -> GameManifest:
    return GameManifest(
        game_id, name, "discovery", ("steam",), "direct-overlay", (), app_id
    )


def home_shelf(root: Path) -> GameShelf:
    """Two installed mod-ready games, an uninstalled catalog game, and a GOG game."""
    catalog = (
        manifest("cronos", "Cronos: The New Dawn", 2101960),
        manifest("stellar-blade", "Stellar Blade", 3489700),
        manifest("dawnwalker", "The Blood of Dawnwalker", 3751260),
    )
    games = (
        InstalledGame("Steam", "2101960", "Cronos", root / "Cronos", True),
        InstalledGame(
            "Steam", "3489700", "Stellar Blade™", root / "SB", True, 5 * 10**9
        ),
        InstalledGame("GOG", "1207", "Hades", root / "Hades", True),
    )
    return build_shelf(catalog, PakGameCatalog(), InstalledScan(games, ()), (root,))


class TuiFixture(unittest.IsolatedAsyncioTestCase):
    """Shared host fakes; holds no tests so subclasses don't rerun each other's."""

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
        self.scanner = FakeShelfScanner(home_shelf(self.root))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _app(
        self,
        members: dict[str, bytes],
        hyprland: FakeHyprland | None = None,
        ayaka_pages: FakeAyakaPages | None = None,
        ayaka_session: FakeAyakaSession | None = None,
        runner: FakeCommandRunner | None = None,
    ) -> OmaModsApp:
        host = TuiHost(
            self.config,
            self.root / "store",
            {},
            self.config_files,
            self.site,
            FakeArchiveReader(members),
            hyprland or runner or FakeCommandRunner(),
            self.launcher,
            FakePaksLocator(self.paks),
            Path("/bin/omamods"),
            self.root / "applications",
            self.scanner,
            "brave" if hyprland else None,
            RetryPolicy(sleep=FakeSleep()),
            ayaka_pages=ayaka_pages,
            ayaka_session=ayaka_session.opener if ayaka_session else None,
            downloads=self.root / "Downloads",
        )
        return OmaModsApp(ModsService(host))

    async def _wait_for_shelf(self, app: OmaModsApp, pilot) -> None:
        await app.workers.wait_for_complete()
        await pilot.pause()

    async def _open_stellar_blade_and_add(self, app: OmaModsApp, pilot) -> None:
        await self._wait_for_shelf(app, pilot)
        await pilot.press("down", "enter", "a")
        app.screen.query_one(Input).value = URL
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()


class TuiTests(TuiFixture):
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

    def _install_other_mod(self, asset: str) -> None:
        """Record Ayaka mod 2 as owning ~mods/Other_P.utoc, carrying ``asset``."""
        (self.root / "store/ayaka/archives/stellar-blade/2").mkdir(parents=True)
        utoc = self.paks / "~mods/Other_P.utoc"
        utoc.parent.mkdir(parents=True, exist_ok=True)
        utoc.write_bytes(utoc_bytes((asset,)))
        record = self.root / "store/ayaka/state/stellar-blade/2/9.json"
        record.parent.mkdir(parents=True)
        owned = {"relative_path": "~mods/Other_P.utoc", "sha256": "x"}
        record.write_text(json.dumps({"paks": str(self.paks), "assets": [owned]}))

    async def test_install_warns_about_assets_another_mod_replaces(self) -> None:
        members = {
            "Black/Zed_P.utoc": utoc_bytes(("Art/Hero/Jacket.uasset",)),
            "Black/Zed_P.ucas": b"cas",
            "Black/Zed_P.pak": directory_pak_bytes(()),  # IoStore's stub pak.
        }
        app = self._app(members)
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            # Recorded after the add so the new mod, not this one, is selected.
            self._install_other_mod("Art/Hero/Jacket.uasset")
            await pilot.press("i")
            # The install worker waits on the dialog, so pause instead of joining it.
            for _ in range(20):
                await pilot.pause(0.05)
                if isinstance(app.screen, ConfirmDialog):
                    break
            self.assertIsInstance(app.screen, ConfirmDialog)
            details = app.screen.details
            self.assertIn("Asset collisions (likely load order):", details)
            self.assertIn("overrides Mod 2: 1 asset(s) (jacket)", details)
            self.assertIn("Zed_P loads over Other_P", details)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            inspector = app.screen.query_one("#mod-collisions", Static)
            self.assertIn("overrides Mod 2", str(inspector.render()))

    async def test_every_variant_is_ticked_and_installs(self) -> None:
        app = self._app({"Mod/Black/b.pak": b"b", "Mod/White/w.pak": b"w"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await pilot.press("i", "enter", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual((self.paks / "~mods/Black/b.pak").read_bytes(), b"b")
            self.assertEqual((self.paks / "~mods/White/w.pak").read_bytes(), b"w")
            await pilot.press("u", "y")
            await pilot.pause()
            self.assertFalse((self.paks / "~mods/Black/b.pak").exists())
            self.assertFalse((self.paks / "~mods/White/w.pak").exists())

    async def test_unticked_variant_is_left_out(self) -> None:
        app = self._app({"Mod/Black/b.pak": b"b", "Mod/White/w.pak": b"w"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await pilot.press("i", "space", "enter", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertTrue((self.paks / "~mods/White/w.pak").is_file())
            self.assertFalse((self.paks / "~mods/Black").exists())

    async def test_unticking_every_variant_installs_nothing(self) -> None:
        app = self._app({"Mod/Black/b.pak": b"b", "Mod/White/w.pak": b"w"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await pilot.press("i", "space", "down", "space", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertFalse((self.paks / "~mods").exists())

    async def test_alternative_variants_start_unticked_and_exclude_each_other(
        self,
    ) -> None:
        # Regression: colours of one outfit share file names; installing both
        # let the game load both and pick one silently.
        app = self._app({"Mod/Black/s.pak": b"b", "Mod/White/s.pak": b"w"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            await pilot.press("i", "space", "down", "space", "enter", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual((self.paks / "~mods/White/s.pak").read_bytes(), b"w")
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

    async def test_removing_the_shown_file_moves_the_window_on(self) -> None:
        self.site.premium = False
        window = "brave-www.nexusmods.com__stellarblade_mods_1-Default"
        hyprland = FakeHyprland([{"address": "0xab", "initialClass": window}])
        app = self._app({}, hyprland)
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            log = download_log(self.root / "store")
            shown = next(s for s in log.statuses() if s.file_id == 7)
            app.service.remove_download(shown)
            opened = [c for c in self.launcher.launched if c[0] == "brave"]
            self.assertIn("file_id=8", opened[-1][1])
            self.assertEqual(len(hyprland.closed()), 1)
            self.assertNotIn(7, [s.file_id for s in log.statuses()])

    def _set_browser_state(self, file_id: int, state: str) -> None:
        log = download_log(self.root / "store")
        current = next(s for s in log.statuses() if s.file_id == file_id)
        log.write(replace(current, state=state))

    async def test_nexus_window_hides_once_the_download_starts(self) -> None:
        self.site.premium = False
        window = "brave-www.nexusmods.com__stellarblade_mods_1-Default"
        hyprland = FakeHyprland([{"address": "0xab", "initialClass": window}])
        app = self._app({}, hyprland)
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            app.advance_browser_downloads()
            self.assertEqual(hyprland.hidden(), [])  # No click yet.
            self._set_browser_state(7, DOWNLOADING)
            app.advance_browser_downloads()
            app.advance_browser_downloads()
            self.assertEqual(len(hyprland.hidden()), 1)  # Hidden once, not per poll.
            self.assertIn("address:0xab", hyprland.hidden()[0])
            self._set_browser_state(7, FAILED)
            app.advance_browser_downloads()
            await pilot.pause()
            reopened = [c for c in self.launcher.launched if c[0] == "brave"]
            self.assertEqual(len(reopened), 2)
            self.assertIn("file_id=7", reopened[1][1])
            messages = [str(n.message) for n in app._notifications]
            self.assertTrue(any("download failed; reopened" in m for m in messages))

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
            # On the mods screen D grows the downloads panel; :queue opens this.
            await self._command(app, pilot, "queue")
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
            await self._wait_for_shelf(app, pilot)
            games = app.screen.query_one("#games", OptionList)
            # Index 0 is the "MOD-READY" heading, which the cursor skips.
            self.assertEqual(games.highlighted, 1)
            await pilot.press("j")
            self.assertEqual(games.highlighted, 2)
            await pilot.press("k")
            self.assertEqual(games.highlighted, 1)
            await pilot.press("G")
            self.assertEqual(games.highlighted_option.id, "gog:1207")
            await pilot.press("g", "g")
            self.assertEqual(games.highlighted, 1)
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

    def _stage_by_hand(self, mod_id: int, name: str) -> None:
        archive = self.root / f"store/archives/stellar-blade/{mod_id}/0/{name}.zip"
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"z")

    async def test_hand_staged_mod_fetches_details_and_picture(self) -> None:
        # Regression: `omamods nexus install` stages no mod.json, so no picture.
        self._stage_by_hand(1, "Black")
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("down", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertIsNotNone(app.screen.current.info)
            self.assertEqual(app.screen.current.picture.name, "picture.png")

    async def test_hand_staged_mod_without_key_stays_offline(self) -> None:
        self.config_files.contents.clear()
        self._stage_by_hand(1, "Black")
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("down", "enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertIsNone(app.screen.current.info)
            self.assertEqual(app._notifications.__len__(), 0)

    async def _open_mods_with(self, app: OmaModsApp, pilot, names: dict[int, str]):
        for mod_id, name in names.items():
            self._stage_by_hand(mod_id, name)
        await self._wait_for_shelf(app, pilot)
        await pilot.press("down", "enter")
        await pilot.pause()
        return app.screen

    async def test_slash_filters_mods_as_you_type(self) -> None:
        self.config_files.contents.clear()  # Keep hand-staged titles offline.
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            screen = await self._open_mods_with(app, pilot, {2: "a", 3: "b", 14: "c"})
            await pilot.press("slash", "4")
            await pilot.pause()
            self.assertEqual([m.mod_id for m in screen.shown], [14])
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(screen.shown), 3)
            self.assertIs(app.screen, screen)

    async def test_enter_keeps_filter_n_cycles_and_esc_clears(self) -> None:
        self.config_files.contents.clear()
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            screen = await self._open_mods_with(app, pilot, {2: "a", 3: "b", 4: "c"})
            mods = screen.query_one("#mods", OptionList)
            await pilot.press("slash", "m", "o", "d", "enter", "n")
            await pilot.pause()
            self.assertEqual(screen.current.mod_id, 3)
            self.assertIn("/mod (3/3)", mods.border_title)
            screen.search("mod 4")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(screen.shown), 3)
            self.assertEqual(screen.current.mod_id, 4)
            await pilot.press("escape")
            self.assertIsInstance(app.screen, GamesScreen)

    async def test_unmatched_search_restores_every_mod(self) -> None:
        self.config_files.contents.clear()
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            screen = await self._open_mods_with(app, pilot, {2: "a", 3: "b"})
            screen.search("zzz")
            await pilot.pause()
            self.assertEqual(len(screen.shown), 2)
            messages = [str(n.message) for n in app._notifications]
            self.assertIn("E486: Pattern not found: zzz", messages)

    async def test_h_blurs_then_hides_nexus_flagged_mods_and_remembers_it(self) -> None:
        self.site.adult = True
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open_stellar_blade_and_add(app, pilot)
            screen = app.screen
            mods = screen.query_one("#mods", OptionList)
            self.assertIn("18+", describe_mod(screen.current, True))
            preview = screen.query_one(PicturePreview)
            self.assertEqual(preview.showing, (screen.current.picture, True))
            await pilot.press("H")
            await pilot.pause()
            self.assertEqual(screen.shown, ())
            self.assertIn("1 NSFW hidden", str(mods.border_subtitle))
            await pilot.press("escape", "enter")
            await pilot.pause()
            self.assertEqual(app.screen.shown, ())

    async def test_m_marks_a_mod_nsfw_by_hand(self) -> None:
        self.config_files.contents.clear()
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            screen = await self._open_mods_with(app, pilot, {2: "a", 3: "b"})
            await pilot.press("m", "H")
            await pilot.pause()
            self.assertEqual([m.mod_id for m in screen.shown], [3])
            await pilot.press("H")
            await pilot.pause()
            self.assertTrue(screen.mod_is_adult(screen.mods[0]))
            app.run_command_line("nsfw unmark")
            app.run_command_line("nsfw wat")
            await pilot.pause()
            # Hiding mod 2 moved the cursor to mod 3, which unmark targets.
            self.assertEqual(screen.current.mod_id, 3)
            self.assertFalse(screen.mod_is_adult(screen.current))
            self.assertTrue(screen.mod_is_adult(screen.mods[0]))
            messages = [str(n.message) for n in app._notifications]
            self.assertTrue(any("expected one of" in m for m in messages))

    async def test_api_key_prompt_saves_key(self) -> None:
        self.config_files.contents.clear()
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("K")
            app.screen.query_one(Input).value = "newkey"
            await pilot.press("enter")
            await pilot.pause()
            self.assertIn('api_key = "newkey"', self.config_files.contents[self.config])


class FailingShelfScanner:
    """Raise like an unreadable games catalog would."""

    def __call__(self, settings: UserSettings) -> GameShelf:
        raise ValueError("games directory 'games': expected an existing directory")


class HomeScreenTests(TuiFixture):
    def _card_text(self, app: OmaModsApp) -> str:
        console = Console(width=100, record=True, color_system=None, file=StringIO())
        console.print(app.screen.query_one("#game-info", Static).content)
        return console.export_text()

    async def test_card_shows_highlighted_game_folder(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("down")
            await pilot.pause()
            card = self._card_text(app)
            self.assertIn(str(self.root / "SB"), card)
            self.assertIn("5.0 GB", card)
            self.assertIn("0 mod(s) staged", card)
            self.assertIn("3 installed", app.screen.sub_title)

    async def test_o_opens_the_install_folder(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("o")
            self.assertEqual(
                self.launcher.launched[-1], ("xdg-open", str(self.root / "Cronos"))
            )

    async def test_unsupported_game_stays_home_with_a_notice(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            await pilot.press("G", "enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, GamesScreen)
            messages = [str(n.message) for n in app._notifications]
            self.assertTrue(any("Hades: installing mods" in m for m in messages))

    async def test_search_and_rescan_keep_the_selection(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            screen = app.screen
            screen.search("BLOOD")
            self.assertEqual(screen.selected_entry().key, "dawnwalker")
            await pilot.press("r")
            await self._wait_for_shelf(app, pilot)
            self.assertEqual(self.scanner.scans, 2)
            self.assertEqual(screen.selected_entry().key, "dawnwalker")
            screen.search("zzz")
            self.assertEqual(screen.selected_entry().key, "dawnwalker")

    async def test_slash_filters_games_and_esc_keeps_the_found_one(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            screen = app.screen
            games = screen.query_one("#games", OptionList)
            total = games.option_count
            await pilot.press("slash", *"blood", "enter")
            await pilot.pause()
            self.assertLess(games.option_count, total)
            self.assertEqual(screen.selected_entry().key, "dawnwalker")
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(games.option_count, total)
            self.assertEqual(screen.selected_entry().key, "dawnwalker")

    async def test_unmatched_typing_shows_a_hint_row(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            games = app.screen.query_one("#games", OptionList)
            await pilot.press("slash", "z", "z")
            await pilot.pause()
            self.assertEqual(games.option_count, 1)
            self.assertIn(
                "No matches for /zz", str(games.get_option_at_index(0).prompt)
            )
            self.assertIn(
                "no matches", str(app.screen.query_one("#command-hint").render())
            )

    async def test_w_lists_warnings(self) -> None:
        self.scanner.shelf = GameShelf(self.scanner.shelf.entries, (), ("bad vdf",))
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            setup = str(app.screen.query_one("#setup", Static).render())
            self.assertIn("1 warning(s)", setup)
            await pilot.press("w")
            self.assertIsInstance(app.screen, InfoDialog)
            self.assertEqual(app.screen.details, "bad vdf")

    async def test_scan_failure_is_reported(self) -> None:
        self.scanner = FailingShelfScanner()
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            messages = [str(n.message) for n in app._notifications]
            self.assertTrue(any("Game scan failed" in m for m in messages))
            self.assertFalse(app.screen.query_one("#games", OptionList).loading)


if __name__ == "__main__":
    unittest.main()


class ScannedGameServiceTests(TuiFixture):
    def test_scan_remembers_unreal_games_for_the_nxm_handler(self) -> None:
        game = PakOverlayGame(
            "remnant2",
            "Remnant II",
            "remnant2",
            Path("Remnant2/Content/Paks"),
            "~mods",
            (frozenset({".pak"}),),
            self.root / "Remnant2",
        )
        entry = ShelfEntry("steam:1", "Remnant II", MOD_READY, (), None, game)
        shelf = self.scanner.shelf
        self.scanner.shelf = replace(shelf, entries=(*shelf.entries, entry))
        service = self._app({}).service
        service.shelf()
        self.assertIs(service.catalog.for_domain("remnant2"), game)
        reloaded = ModsService(service.host)
        self.assertEqual(reloaded.catalog.get("remnant2"), game)
