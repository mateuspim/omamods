"""Repository releases for the TUI: list built-in sources and fetch their files.

Every source in ``release_sources`` shows up in its game's mods list before
anything is downloaded; ``d`` asks the forge for the newest release and
downloads its archive, and opening the screen checks for a newer one.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from omamods.mod_fetch import download_log
from omamods.pak_games import PakOverlayGame
from omamods.release_api import (
    LatestRelease,
    ReleaseAsset,
    ReleaseTransport,
    fetch_latest_release,
)
from omamods.release_sources import release_source, sources_for
from omamods.release_staging import (
    load_release_mod,
    release_root,
    stage_release_asset,
    stage_release_details,
)
from omamods.staging import StagedMod

if TYPE_CHECKING:
    from omamods.tui.service import ModsService


class ReleaseSite:
    """Release actions behind the service; e.g. ``service.release.download(mgsv, 1)``."""

    def __init__(self, service: "ModsService") -> None:
        self.service = service

    def root(self) -> Path:
        """Locate release staging and records; e.g. ``service.release.root()``."""
        return release_root(self.service.settings.storage_root)

    def _transport(self) -> ReleaseTransport:
        transport = self.service.host.release_transport
        if transport is None:
            raise ValueError(
                "release downloads: expected a release transport in TuiHost"
            )
        return transport

    def staged_mods(self, game: PakOverlayGame) -> tuple[StagedMod, ...]:
        """List the game's release mods; e.g. ``service.release.staged_mods(mgsv)``."""
        root = self.root()
        return tuple(load_release_mod(root, game, s) for s in sources_for(game.game_id))

    def staged_mod(self, game: PakOverlayGame, mod_id: int) -> StagedMod:
        """Reload one; e.g. ``service.release.staged_mod(mgsv, 1)``."""
        return load_release_mod(self.root(), game, release_source(game.game_id, mod_id))

    def page_url(self, game: PakOverlayGame, mod_id: int) -> str:
        """Link the repository; e.g. ``service.release.page_url(mgsv, 1)``."""
        return release_source(game.game_id, mod_id).page_url

    def _latest(self, game: PakOverlayGame, mod_id: int) -> LatestRelease:
        source = release_source(game.game_id, mod_id)
        release = fetch_latest_release(self._transport(), source)
        stage_release_details(self.root(), game, source, release)
        return release

    def refresh(self, game: PakOverlayGame, mod_id: int) -> StagedMod:
        """Record the newest release; e.g. ``service.release.refresh(mgsv, 1)``."""
        self._latest(game, mod_id)
        return self.staged_mod(game, mod_id)

    def download(self, game: PakOverlayGame, mod_id: int) -> tuple[Path, ...]:
        """Fetch the newest release's archives; e.g. ``service.release.download(mgsv, 1)``."""
        release = self._latest(game, mod_id)
        staged = self.staged_mod(game, mod_id).archives
        missing = tuple(a for a in release.assets if a.file.file_id not in staged)
        return tuple(self._fetch(game, mod_id, asset) for asset in missing)

    def _fetch(self, game: PakOverlayGame, mod_id: int, asset: ReleaseAsset) -> Path:
        source = release_source(game.game_id, mod_id)
        log = download_log(self.service.settings.storage_root)
        transport, retry = self._transport(), self.service.host.retry
        return stage_release_asset(
            transport, self.root(), game, source, asset, log, retry
        )

    def retry(self, game: PakOverlayGame, mod_id: int, file_id: int) -> Path:
        """Download a queue entry again; e.g. ``service.release.retry(mgsv, 1, 7)``."""
        release = self._latest(game, mod_id)
        asset = next((a for a in release.assets if a.file.file_id == file_id), None)
        if asset is None:
            names = [a.file.file_name for a in release.assets]
            raise ValueError(
                f"release file={file_id}: expected one of the newest release's "
                f"{names!r}; older releases are not downloaded again"
            )
        return self._fetch(game, mod_id, asset)
