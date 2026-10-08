"""AyakaMods for the TUI: add a mod, open its page, and take the browser's file.

The site needs a logged-in browser to download, so OmaMods opens the mod page,
watches the downloads folder, and moves the finished archive into staging.
"""

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from omamods.ayaka_pages import (
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
from omamods.browser_windows import ayaka_window_class
from omamods.pak_games import PakOverlayGame
from omamods.staging import AYAKA_SITE, StagedMod, list_staged_mods, load_staged_mod

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
