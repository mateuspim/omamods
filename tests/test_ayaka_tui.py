"""Add an AyakaMods mod in the TUI, take the browser's file, install, uninstall."""

from pathlib import Path

from textual.widgets import Input

from omamods.tui.app import OmaModsApp
from omamods.tui.mods_screen import ModsScreen, describe_mod
from tests.fakes import FakeAyakaPages, FakeAyakaSession
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


class AyakaTuiFixture(TuiFixture):
    """Shared steps; holds no tests so subclasses don't rerun each other's."""

    async def _add_ayaka_mod(self, app: OmaModsApp, pilot, url: str) -> ModsScreen:
        await self._wait_for_shelf(app, pilot)
        await pilot.press("down", "enter", "a")
        app.screen.query_one(Input).value = url
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        # A file picker may already sit on top of the mods screen.
        return next(s for s in app.screen_stack if isinstance(s, ModsScreen))

    async def _settle(self, app: OmaModsApp, pilot) -> None:
        # Downloads run in a worker that starts another; let both finish.
        for _ in range(3):
            await app.workers.wait_for_complete()
            await pilot.pause()


class AyakaTuiTests(AyakaTuiFixture):
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


DOWNLOAD_URL = "https://ayakamods.com/mods/7322/download"
COOKIE = "347376%2CAbC"


class AyakaLoginTuiTests(AyakaTuiFixture):
    def setUp(self) -> None:
        super().setUp()
        self.session = FakeAyakaSession()
        login = f'\n[ayaka]\nlogin_cookie = "{COOKIE}"\n'
        self.config_files.contents[self.config] += login

    def _login_app(self, members: dict[str, bytes]) -> OmaModsApp:
        pages = ayaka_pages("Stellar Blade")
        return self._app(members, ayaka_pages=pages, ayaka_session=self.session)

    def _serve_two_files(self) -> None:
        names = ((11, "Black.zip"), (12, "Red.zip"))
        links = "".join(
            f'<a href="/mods/x.7322/download?file={n}">{name}</a>' for n, name in names
        )
        page = f'<html data-logged-in="true">{links}</html>'
        self.session.serve_page(DOWNLOAD_URL, page)
        for n, name in names:
            url = f"https://ayakamods.com/mods/x.7322/download?file={n}"
            self.session.serve_file(url, name, name.encode())

    async def test_the_only_file_downloads_straight_into_staging(self) -> None:
        self.session.serve_file(DOWNLOAD_URL, "Outfit.zip", b"zip")
        app = self._login_app({"Black/s.pak": b"pak"})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._add_ayaka_mod(app, pilot, AYAKA_URL)
            await self._settle(app, pilot)
            staged = self.root / "store/ayaka/archives/stellar-blade/7322/1/Outfit.zip"
            self.assertEqual(staged.read_bytes(), b"zip")
            self.assertEqual(self.launcher.launched, [])  # No browser.
            self.assertEqual(self.session.cookies[-1], COOKIE)
            (status,) = app.service.downloads()
            self.assertEqual((status.site, status.file_name), ("ayaka", "Outfit.zip"))
            await pilot.press("i", "y")
            await self._settle(app, pilot)
            self.assertEqual((self.paks / "~mods/Black/s.pak").read_bytes(), b"pak")

    async def test_several_files_open_the_picker(self) -> None:
        self._serve_two_files()
        app = self._login_app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._add_ayaka_mod(app, pilot, AYAKA_URL)
            await self._settle(app, pilot)
            await pilot.press("space", "enter")  # Untick Black, download Red.
            await self._settle(app, pilot)
            folder = self.root / "store/ayaka/archives/stellar-blade/7322"
            self.assertEqual((folder / "12/Red.zip").read_bytes(), b"Red.zip")
            self.assertFalse((folder / "11").exists())

    async def test_retry_downloads_an_ayaka_entry_again(self) -> None:
        self._serve_two_files()
        app = self._login_app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._add_ayaka_mod(app, pilot, AYAKA_URL)
            await self._settle(app, pilot)
            await pilot.press("enter")
            await self._settle(app, pilot)
            red = self.root / "store/ayaka/archives/stellar-blade/7322/12/Red.zip"
            red.unlink()
            status = next(s for s in app.service.downloads() if s.file_id == 12)
            self.assertTrue(app.service.retry(status))
            self.assertEqual(red.read_bytes(), b"Red.zip")

    async def test_an_expired_cookie_falls_back_to_the_browser(self) -> None:
        self.session.serve_page(DOWNLOAD_URL, '<html data-logged-in="false"></html>')
        app = self._login_app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._add_ayaka_mod(app, pilot, AYAKA_URL)
            await self._settle(app, pilot)
            self.assertEqual(self.launcher.launched[-1], ("xdg-open", PAGE_URL))

    async def test_login_command_saves_the_cookie(self) -> None:
        del self.config_files.contents[self.config]
        app = self._login_app({})
        async with app.run_test(size=(140, 45)) as pilot:
            await self._wait_for_shelf(app, pilot)
            app.run_command_line(f":ayaka-login xf_user={COOKIE}")
            await pilot.pause()
            self.assertEqual(app.service.ayaka.login_cookie(), COOKIE)
