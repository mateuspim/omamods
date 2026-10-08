"""AyakaMods for the TUI: add a mod and download its files.

The site serves files only to a logged-in user. With the user's login
cookie OmaMods downloads them itself, like Nexus files; without it, it
opens the mod page, watches the downloads folder, and moves the finished
archive into staging.
"""

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from omamods.ayaka_config import (
    load_login_cookie,
    normalize_cookie,
    save_login_cookie,
)
from omamods.ayaka_download import (
    AyakaLoginRequired,
    AyakaOffer,
    AyakaSession,
    list_offers,
)
from omamods.ayaka_fetch import stage_ayaka_offer
from omamods.ayaka_pages import (
    LOGIN_URL,
    AyakaPage,
    AyakaPageTransport,
    fetch_mod_details,
    mod_page_url,
    parse_ayaka_page,
)
from omamods.ayaka_staging import (
    ayaka_root,
    claim_ayaka_archive,
    require_game,
    stage_ayaka_details,
)
from omamods.ayaka_wait import AyakaWaits
from omamods.browser_windows import ayaka_login_window_class, ayaka_window_class
from omamods.mod_fetch import download_log
from omamods.pak_games import PakOverlayGame
from omamods.mod_sites import AYAKA_SITE
from omamods.staging import StagedMod, list_staged_mods, load_staged_mod

if TYPE_CHECKING:
    from omamods.tui.service import ModsService


class AyakaSite:
    """AyakaMods actions behind the service; e.g. ``service.ayaka.add(game, url)``."""

    def __init__(self, service: "ModsService") -> None:
        self.service = service
        downloads = service.host.downloads
        self.waits = AyakaWaits(downloads) if downloads is not None else None

    def root(self) -> Path:
        """Locate Ayaka staging and records; e.g. ``service.ayaka.root()``."""
        return ayaka_root(self.service.settings.storage_root)

    def _pages(self) -> AyakaPageTransport:
        pages = self.service.host.ayaka_pages
        if pages is None:
            raise ValueError("AyakaMods pages: expected a page transport in TuiHost")
        return pages

    def _waits(self) -> AyakaWaits:
        if self.waits is None:
            raise ValueError("AyakaMods downloads: expected a downloads folder")
        return self.waits

    def staged_mods(self, game: PakOverlayGame) -> tuple[StagedMod, ...]:
        """List the game's Ayaka mods; e.g. ``service.ayaka.staged_mods(co)``."""
        mods = list_staged_mods(self.root(), game)
        return tuple(replace(mod, site=AYAKA_SITE) for mod in mods)

    def staged_mod(self, game: PakOverlayGame, mod_id: int) -> StagedMod:
        """Reload one Ayaka mod; e.g. ``service.ayaka.staged_mod(co, 7311)``."""
        return replace(load_staged_mod(self.root(), game, mod_id), site=AYAKA_SITE)

    def game_for(self, url: str) -> PakOverlayGame:
        """Find the installed game a mod page is for; e.g. ``service.ayaka.game_for(url)``."""
        details = fetch_mod_details(self._pages(), parse_ayaka_page(url.strip()))
        for game in self.service.games():
            try:
                require_game(details, game)
            except ValueError:
                continue
            return game
        raise ValueError(
            f"AyakaMods game={details.game_name!r}: expected an installed game "
            "OmaMods can mod; press r on the home screen to rescan"
        )

    def add(self, game: PakOverlayGame, url: str) -> StagedMod:
        """Stage a mod's page details; e.g. ``service.ayaka.add(co, url)``."""
        page = parse_ayaka_page(url.strip())
        transport = self.service.host.transport
        root = self.root()
        mod = stage_ayaka_details(self._pages(), transport, game, page, root)
        return replace(mod, site=AYAKA_SITE)

    def watch(self, game: PakOverlayGame, mod: StagedMod) -> str:
        """Open the page and wait for its file; e.g. ``service.ayaka.watch(co, mod)``."""
        waits = self._waits()
        replaced = waits.start(game.game_id, mod.mod_id)
        self.service.open_nexus(mod_page_url(AyakaPage(mod.mod_id)))
        stopped = (
            f" Stopped waiting for mod {replaced.mod_id}."
            if replaced and replaced.mod_id != mod.mod_id
            else ""
        )
        return (
            f"{mod.title}: download it in the browser; OmaMods takes the file "
            f"from {waits.downloads}.{stopped}"
        )

    def cancel(self) -> str:
        """Stop waiting; e.g. ``service.ayaka.cancel()``."""
        stopped = self._waits().cancel()
        if stopped is None:
            return "Not waiting for an AyakaMods download."
        return f"Stopped waiting for AyakaMods mod {stopped.mod_id}."

    def take_arrivals(self) -> tuple[str, ...]:
        """Stage finished downloads; e.g. ``service.ayaka.take_arrivals()``."""
        result = self.waits.arrivals() if self.waits else None
        if result is None:
            return ()
        wait, archives = result
        game = self.service.catalog.get(wait.game_id)
        files = [
            claim_ayaka_archive(self.root(), game, wait.mod_id, archive)
            for archive in archives
        ]
        self.service.windows.close_class(ayaka_window_class(wait.mod_id))
        title = self.staged_mod(game, wait.mod_id).title
        return tuple(
            f"{title}: {file.file_name} arrived; press i to install" for file in files
        )

    def login_cookie(self) -> str:
        """Read the saved xf_user cookie, or ''; e.g. ``service.ayaka.login_cookie()``."""
        host = self.service.host
        return load_login_cookie(host.config_path, host.config_files)

    def save_login(self, cookie: str) -> None:
        """Store the browser's xf_user cookie; e.g. ``service.ayaka.save_login(value)``."""
        host = self.service.host
        save_login_cookie(
            host.config_path, host.fallback_root, cookie, host.config_files
        )

    def open_login(self) -> None:
        """Open the login page in its own window; e.g. ``service.ayaka.open_login()``."""
        # An app window like the mod pages', so the same window rule floats it.
        self.service.open_nexus(LOGIN_URL)

    def close_login(self) -> int:
        """Close the login window once done; e.g. ``service.ayaka.close_login()``."""
        return self.service.windows.close_class(ayaka_login_window_class())

    def clipboard_cookie(self) -> str | None:
        """Read a copied xf_user value, if any; e.g. ``service.ayaka.clipboard_cookie()``."""
        code, text = self.service.host.runner.run(("wl-paste", "--no-newline"))
        if code:
            return None
        try:
            return normalize_cookie(text)
        except ValueError:
            return None  # Anything else on the clipboard is not ours to read.

    def _session(self) -> AyakaSession:
        cookie = self.login_cookie()
        if not cookie:
            raise AyakaLoginRequired(
                "AyakaMods login cookie: expected one; save it with :ayaka-login"
            )
        opener = self.service.host.ayaka_session
        if opener is None:
            raise ValueError("AyakaMods session: expected a session opener in TuiHost")
        return opener(cookie)

    def offers(self, mod: StagedMod) -> tuple[AyakaOffer, ...]:
        """List a mod's files as the logged-in user; e.g. ``service.ayaka.offers(mod)``."""
        return list_offers(self._session(), AyakaPage(mod.mod_id))

    def download(self, game: PakOverlayGame, mod_id: int, offer: AyakaOffer) -> Path:
        """Download one file into staging; e.g. ``service.ayaka.download(co, 7311, o)``."""
        service = self.service
        log = download_log(service.settings.storage_root)
        return stage_ayaka_offer(
            self._session(), self.root(), game, mod_id, offer, log, service.host.retry
        )

    def retry(self, game: PakOverlayGame, mod_id: int, file_id: int) -> Path:
        """Download a queue entry again; e.g. ``service.ayaka.retry(co, 7311, 7)``."""
        offers = self.offers(self.staged_mod(game, mod_id))
        # A page's only file has no attachment ID; any entry of that mod is it.
        offer = next((o for o in offers if o.attachment_id == file_id), None)
        if offer is None and len(offers) == 1:
            offer = offers[0]
        if offer is None:
            raise ValueError(
                f"AyakaMods mod {mod_id} file={file_id}: expected it among "
                f"{[o.label for o in offers]!r}"
            )
        return self.download(game, mod_id, offer)
