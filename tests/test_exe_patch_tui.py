"""Built-in exe patches appear in a game's mods screen like any other mod."""

from pathlib import Path
import unittest
from unittest.mock import patch

from omamods.asset_plans import game_variants, plan_game_assets
from omamods.display_sizes import aspect_name, read_monitors, resolution_choices
from omamods.exe_patch_games import EXE_PATCH_GAMES
from omamods.game_shelf import GameShelf, build_shelf
from omamods.installed_games import InstalledGame, InstalledScan
from omamods.manifests import GameManifest
from omamods.mod_sites import PATCH_SITE
from omamods.pak_games import PAK_OVERLAY_GAMES, PakGameCatalog
from omamods.tui.dialogs import ConfirmDialog
from omamods.tui.exe_patch_actions import PatchModsScreen
from omamods.tui.resolution_picker import ResolutionPicker
from tests.fakes import FakeCommandRunner, FakeShelfScanner
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
MONITORS = '[{"width": 3440, "height": 1440}, {"width": 1920, "height": 1200}]'
FOCUSED = (
    '[{"name": "DP-4", "model": "GP2711", "width": 1920, "height": 1200},'
    ' {"name": "DP-5", "model": "34R83Q", "width": 3440, "height": 1440,'
    ' "focused": true}]'
)


def mgr_shelf(root: Path) -> GameShelf:
    """METAL GEAR RISING installed under root."""
    game = InstalledGame("Steam", "235460", "MGR", root / "MGR", True)
    return build_shelf((MGR,), PakGameCatalog(), InstalledScan((game,), ()), (root,))


class DisplaySizeTests(unittest.TestCase):
    def test_reads_hyprland_monitors_focused_first(self) -> None:
        runner = FakeCommandRunner(output=FOCUSED)
        monitors = read_monitors(runner)
        self.assertEqual([m.name for m in monitors], ["DP-5", "DP-4"])
        self.assertEqual(monitors[0].model, "34R83Q")
        self.assertEqual(runner.commands, [("hyprctl", "monitors", "-j")])

    def test_no_hyprland_means_no_monitors(self) -> None:
        self.assertEqual(read_monitors(FakeCommandRunner(127)), ())
        self.assertEqual(read_monitors(FakeCommandRunner(output="nope")), ())
        self.assertEqual(read_monitors(FakeCommandRunner(output="{}")), ())

    def test_aspect_names(self) -> None:
        cases = {
            (3440, 1440): "21:9",
            (2560, 1080): "21:9",
            (5120, 1440): "32:9",
            (2560, 1440): "16:9",
            (1920, 1200): "16:10",
            (1024, 768): "4:3",
            (2000, 1000): "2:1",
        }
        for (width, height), name in cases.items():
            self.assertEqual(aspect_name(width, height), name)

    def test_choices_label_monitors_and_disable_narrow_ones(self) -> None:
        choices = resolution_choices(read_monitors(FakeCommandRunner(output=FOCUSED)))
        self.assertEqual(choices[0].size, "3440x1440")
        self.assertIn("21:9", choices[0].label)
        self.assertIn("DP-5 · 34R83Q  (focused)", choices[0].label)
        narrow = choices[1]
        self.assertEqual((narrow.size, narrow.allowed), ("1920x1200", False))
        self.assertIn("needs 16:9 or wider", narrow.label)
        self.assertEqual([c.size for c in choices].count("3440x1440"), 1)
        self.assertTrue(all(c.allowed for c in choices[2:]))


class PatchOnlyGameTests(unittest.TestCase):
    def test_mgr_is_mod_ready_and_refuses_archives(self) -> None:
        entry = mgr_shelf(Path("/games")).entries[0]
        self.assertIs(entry.pak_game, PAK_OVERLAY_GAMES["metalgearrising"])
        game = PAK_OVERLAY_GAMES["metalgearrising"]
        with self.assertRaisesRegex(ValueError, "built-in ultrawide patch"):
            plan_game_assets(("data/mod.dat",), game, None)
        self.assertEqual(game_variants(("a/x.dat", "b/y.dat"), game), ())


class PatchModsScreenTests(TuiFixture):
    def setUp(self) -> None:
        super().setUp()
        self.exe = self.paks / "Game.exe"
        self.exe.write_bytes(b"original")
        self.scanner = FakeShelfScanner(mgr_shelf(self.root))
        self.patch = patch.dict(EXE_PATCH_GAMES, {"metalgearrising": FAKE_GAME})
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        super().tearDown()

    async def _open(self, app, pilot) -> PatchModsScreen:  # type: ignore[no-untyped-def]
        await self._wait_for_shelf(app, pilot)
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, PatchModsScreen)
        return screen

    async def test_enter_opens_mods_with_the_patch_listed_first(self) -> None:
        app = self._app({})
        async with app.run_test(size=(140, 45)) as pilot:
            screen = await self._open(app, pilot)
            self.assertEqual(screen.current.site, PATCH_SITE)
            self.assertEqual(screen.current.title, "Ultrawide patch (built in)")
            await pilot.press("d", "x")
            await pilot.pause()
            self.assertTrue(self.exe.is_file())
            messages = [str(n.message) for n in app._notifications]
            self.assertTrue(any("is built in" in m for m in messages))

    async def test_install_picks_a_monitor_size_then_uninstall_restores(self) -> None:
        app = self._app({}, runner=FakeCommandRunner(output=MONITORS))
        async with app.run_test(size=(140, 45)) as pilot:
            screen = await self._open(app, pilot)
            await pilot.press("i")
            await pilot.pause()
            self.assertIsInstance(app.screen, ResolutionPicker)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, ConfirmDialog)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(self.exe.read_bytes(), b"ORIGINAL3440x1440")
            self.assertEqual(screen.current.installed, frozenset({1}))
            uninstall = self.service_of(app).game_uninstall
            self.assertEqual(uninstall.installed_mods(screen.game), ())
            await pilot.press("u")
            await pilot.pause()
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(self.exe.read_bytes(), b"original")
            messages = [str(n.message) for n in app._notifications]
            self.assertIn("Pick 1080p.", messages)

    async def test_other_size_prefills_a_real_example(self) -> None:
        app = self._app({}, runner=FakeCommandRunner(127))
        async with app.run_test(size=(140, 45)) as pilot:
            await self._open(app, pilot)
            await pilot.press("i")
            await pilot.pause()
            await pilot.press("end", "enter")
            await pilot.pause()
            prompt_value = app.screen.query_one("Input").value
            self.assertEqual(prompt_value, "2560x1080")

    @staticmethod
    def service_of(app):  # type: ignore[no-untyped-def]
        return app.screen.service


if __name__ == "__main__":
    unittest.main()
