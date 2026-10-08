"""Add an AyakaMods mod in the TUI, take the browser's file, install, uninstall."""

from pathlib import Path

from textual.widgets import Input

from omamods.tui.app import OmaModsApp
from omamods.tui.mods_screen import ModsScreen, describe_mod
from tests.fakes import FakeAyakaPages
from tests.test_ayaka_pages import MOD_BLOCK, page_html
from tests.test_tui import TuiFixture

AYAKA_URL = "https://ayakamods.com/mods/sample-outfit.7322/"
PAGE_URL = "https://ayakamods.com/mods/7322/"


def ayaka_pages(game_name: str) -> FakeAyakaPages:
    block = {
        **MOD_BLOCK,
        "name": "Ayaka Outfit",
        "genre": game_name,
        "image": "https://ayakamods.com/data/mod_icons/7/7322.png",
    }
    return FakeAyakaPages({PAGE_URL: page_html(block)})


class AyakaTuiTests(TuiFixture):
    async def _add_ayaka_mod(self, app: OmaModsApp, pilot, url: str) -> ModsScreen:
        await self._wait_for_shelf(app, pilot)
        await pilot.press("down", "enter", "a")
        app.screen.query_one(Input).value = url
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, ModsScreen)
        return app.screen

    def _browser_saves(self, name: str) -> Path:
        downloads = self.root / "Downloads"
        downloads.mkdir(exist_ok=True)
        archive = downloads / name
        archive.write_bytes(b"zip")
        return archive

    async def test_browser_download_is_staged_installed_and_uninstalled(
        self,
    ) -> None:
        app = self._app(
            {"Black/s.pak": b"pak"}, ayaka_pages=ayaka_pages("Stellar Blade")
        )
        async with app.run_test(size=(140, 45)) as pilot:
            screen = await self._add_ayaka_mod(app, pilot, AYAKA_URL)
            self.assertEqual(self.launcher.launched[-1], ("xdg-open", PAGE_URL))
            download = self._browser_saves("Outfit.zip")
            screen.take_ayaka_arrivals()  # Size seen once...
            screen.take_ayaka_arrivals()  # ...and unchanged: finished.
            await pilot.pause()
            staged = self.root / "store/ayaka/archives/stellar-blade/7322/1/Outfit.zip"
            self.assertEqual((staged.read_bytes(), download.exists()), (b"zip", False))
            self.assertIn("from AyakaMods", describe_mod(screen.current))
            await pilot.press("i", "y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual((self.paks / "~mods/Black/s.pak").read_bytes(), b"pak")
            record = self.root / "store/ayaka/state/stellar-blade/7322/1.json"
            self.assertTrue(record.is_file())
            await pilot.press("u", "y")
            await pilot.pause()
            self.assertFalse((self.paks / "~mods/Black/s.pak").exists())

    async def test_files_already_in_downloads_are_left_alone(self) -> None:
        old = self._browser_saves("Old.zip")
        app = self._app({"a.pak": b"a"}, ayaka_pages=ayaka_pages("Stellar Blade"))
        async with app.run_test(size=(140, 45)) as pilot:
            screen = await self._add_ayaka_mod(app, pilot, AYAKA_URL)
            screen.take_ayaka_arrivals()
            screen.take_ayaka_arrivals()
            self.assertTrue(old.is_file())
            self.assertFalse(
                (self.root / "store/ayaka/archives/stellar-blade/7322/1").exists()
            )

    async def test_mod_for_another_game_is_refused(self) -> None:
        app = self._app({}, ayaka_pages=ayaka_pages("Helldivers 2"))
        async with app.run_test(size=(140, 45)) as pilot:
            await self._add_ayaka_mod(app, pilot, AYAKA_URL)
            self.assertFalse((self.root / "store/ayaka/archives").exists())
            self.assertEqual(self.launcher.launched, [])

    async def test_add_command_finds_the_game_from_the_page(self) -> None:
        app = self._app({}, ayaka_pages=ayaka_pages("Stellar Blade™"))
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            app.run_command_line(f":add {AYAKA_URL}")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertIsInstance(app.screen, ModsScreen)
            self.assertEqual(app.screen.game.game_id, "stellar-blade")
            self.assertEqual(self.launcher.launched[-1], ("xdg-open", PAGE_URL))
