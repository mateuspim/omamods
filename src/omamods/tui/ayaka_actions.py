"""AyakaMods actions for a game's mods screen.

Split from mods_screen.py, which is near the 500-line limit. With the user's
login cookie, files download straight into staging like Nexus files. Without
it (or once it expires) the mod page opens in the browser, and the screen
takes the file once the browser has saved it.
"""

from textual import work

from omamods.ayaka_download import AyakaHostedElsewhere, AyakaLoginRequired, AyakaOffer
from omamods.ayaka_staging import AYAKA_FILE_CATEGORY
from omamods.nexus_api import NexusFile
from omamods.staging import StagedMod
from omamods.tui.dialogs import FilePicker
from omamods.tui.login_dialog import LoginCookiePrompt
from omamods.tui.release_actions import ReleaseScreen


def offer_file(offer: AyakaOffer, index: int) -> NexusFile:
    """Show an offer in the file picker; e.g. ``offer_file(offer, 0)``."""
    # Pickers key rows by file ID; a page's only file has no attachment ID.
    file_id = offer.attachment_id if offer.attachment_id is not None else index
    return NexusFile(file_id, offer.label, AYAKA_FILE_CATEGORY, 0, offer.label)


class AyakaScreen(ReleaseScreen):
    """Base for ModsScreen: add AyakaMods mods and download their files."""

    def fetch_ayaka(self, url: str) -> None:
        """Stage a page, then download its files; e.g. ``screen.fetch_ayaka(url)``."""
        self.notify("Fetching mod details from AyakaMods...")
        self._ayaka_worker(url)

    @work(thread=True)
    def _ayaka_worker(self, url: str) -> None:
        mod = self._attempt(lambda: self.service.ayaka.add(self.game, url))
        if mod is None:
            return
        self.app.call_from_thread(self.reload)
        self._fetch_ayaka_files(mod)

    def download_ayaka(self, mod: StagedMod) -> None:
        """Download (or open the page for) a mod's files; e.g. ``screen.download_ayaka(m)``."""
        self._offers_worker(mod)

    @work(thread=True)
    def _offers_worker(self, mod: StagedMod) -> None:
        self._fetch_ayaka_files(mod)

    def _fetch_ayaka_files(self, mod: StagedMod) -> None:
        if not self.service.ayaka.login_cookie():
            self.app.call_from_thread(self.ask_for_login, mod, "none saved yet")
            return
        try:
            offers = self.service.ayaka.offers(mod)
        except AyakaLoginRequired:
            self.app.call_from_thread(self.ask_for_login, mod, "the saved one expired")
            return
        except AyakaHostedElsewhere as reason:
            self.notify(f"{reason}; opening the page instead.", severity="warning")
            self.watch_ayaka(mod)
            return
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)
            return
        self.app.call_from_thread(self._pick_offers, mod, offers)

    def _pick_offers(self, mod: StagedMod, offers: tuple[AyakaOffer, ...]) -> None:
        if len(offers) == 1:
            self._download_offers(mod, offers)
            return
        files = tuple(offer_file(offer, i) for i, offer in enumerate(offers))
        by_id = dict(zip((f.file_id for f in files), offers))
        picker = FilePicker(f"{mod.title}: choose files to download", files)
        self.app.push_screen(
            picker,
            lambda chosen: chosen
            and self._download_offers(mod, tuple(by_id[f.file_id] for f in chosen)),
        )

    @work(thread=True)
    def _download_offers(self, mod: StagedMod, offers: tuple[AyakaOffer, ...]) -> None:
        self.notify(f"Downloading {len(offers)} file(s) from AyakaMods...")
        for offer in offers:
            path = self._attempt(
                lambda: self.service.ayaka.download(self.game, mod.mod_id, offer)
            )
            if path is not None:
                self.notify(f"{mod.title}: {path.name} downloaded; press i to install")
        self.app.call_from_thread(self.reload)

    def ask_for_login(
        self, mod: StagedMod | None, reason: str, open_page: bool = True
    ) -> None:
        """Open the login page and wait for the cookie; e.g. ``screen.ask_for_login(m, 'expired')``."""
        if open_page:
            self._attempt(self.service.ayaka.open_login)
        prompt = LoginCookiePrompt(reason, self.service.ayaka.clipboard_cookie)
        self.app.push_screen(prompt, lambda cookie: self._login_answered(mod, cookie))

    def _login_answered(self, mod: StagedMod | None, cookie: str | None) -> None:
        if cookie is None:
            self._attempt(self.service.ayaka.close_login)
            if mod is not None:
                self.watch_ayaka(mod)
            return
        try:
            self.service.ayaka.save_login(cookie)
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)
            # The page is already open; only the paste was wrong.
            self.ask_for_login(mod, "that value was not the xf_user cookie", False)
            return
        self._attempt(self.service.ayaka.close_login)
        self.notify("Saved your AyakaMods login.")
        if mod is not None:
            self.download_ayaka(mod)

    def watch_ayaka(self, mod: StagedMod) -> None:
        """Open the mod page and wait for a file; e.g. ``screen.watch_ayaka(mod)``."""
        message = self._attempt(lambda: self.service.ayaka.watch(self.game, mod))
        if message is not None:
            self.notify(message, timeout=20)

    def cancel_ayaka(self) -> None:
        """Stop waiting for a download; e.g. ``screen.cancel_ayaka()``."""
        message = self._attempt(self.service.ayaka.cancel)
        if message is not None:
            self.notify(message)

    def take_ayaka_arrivals(self) -> None:
        """Stage files the browser finished; runs on a timer."""
        messages = self._attempt(self.service.ayaka.take_arrivals)
        if not messages:
            return
        for message in messages:
            self.notify(message, timeout=15)
        self.reload()
