"""Stage repository releases in their own storage area, beside Nexus' staging.

Release mods have no site-wide numbers, so they keep Nexus' layout under
``<storage-root>/release/`` (archives and install records) where their small
fixed IDs cannot meet Nexus or AyakaMods ones::

    release/archives/<game>/<mod_id>/mod.json
    release/archives/<game>/<mod_id>/<asset_id>/<file_name>
    release/state/<game>/<mod_id>/<asset_id>.json

Files of older releases stay listed as OLD_VERSION, like Nexus' own.
"""

from dataclasses import replace
from pathlib import Path

from omamods.cdn_download import RetryPolicy
from omamods.download_queue import DOWNLOADING, DownloadLog
from omamods.mod_fetch import tracked_download
from omamods.mod_sites import RELEASE_SITE
from omamods.nexus_api import NexusFile, NexusModInfo
from omamods.pak_games import PakOverlayGame
from omamods.pak_storage import archive_path
from omamods.release_api import LatestRelease, ReleaseAsset, ReleaseTransport
from omamods.release_sources import ReleaseSource
from omamods.staging import (
    StagedMod,
    load_mod_details,
    load_staged_mod,
    mod_folder,
    save_mod_details,
)

RELEASE_FOLDER = "release"
OLD_RELEASE_CATEGORY = "OLD_VERSION"


def release_root(storage_root: Path) -> Path:
    """Locate release staging and records; e.g. ``release_root(Path('~/mods'))``."""
    return storage_root / RELEASE_FOLDER


def release_info(source: ReleaseSource, version: str) -> NexusModInfo:
    """Describe a source for the details panel; e.g. ``release_info(mgsvfix, '0.0.3')``."""
    summary = f"{source.summary}\n\nReleases: {source.page_url}"
    return NexusModInfo(source.repo, summary, source.owner, version, None)


def _demoted(
    files: tuple[NexusFile, ...], current: frozenset[int]
) -> tuple[NexusFile, ...]:
    return tuple(
        replace(file, category=OLD_RELEASE_CATEGORY)
        for file in files
        if file.file_id not in current
    )


def stage_release_details(
    root: Path, game: PakOverlayGame, source: ReleaseSource, release: LatestRelease
) -> StagedMod:
    """Record the newest release; e.g. ``stage_release_details(root, mgsv, src, rel)``."""
    folder = mod_folder(root, game, source.mod_id)
    newest = tuple(asset.file for asset in release.assets)
    current = frozenset(file.file_id for file in newest)
    older = _demoted(load_mod_details(folder)[1], current)
    save_mod_details(folder, release_info(source, release.tag), newest + older)
    return load_release_mod(root, game, source)


def load_release_mod(
    root: Path, game: PakOverlayGame, source: ReleaseSource
) -> StagedMod:
    """Describe a source, fetched or not; e.g. ``load_release_mod(root, mgsv, src)``."""
    mod = replace(load_staged_mod(root, game, source.mod_id), site=RELEASE_SITE)
    if mod.info is not None:
        return mod
    info = release_info(source, "")
    summary = f"{info.summary}\n\nPress d to download the newest release."
    return replace(mod, info=replace(info, summary=summary))


def stage_release_asset(
    transport: ReleaseTransport,
    root: Path,
    game: PakOverlayGame,
    source: ReleaseSource,
    asset: ReleaseAsset,
    log: DownloadLog,
    retry: RetryPolicy = RetryPolicy(),
) -> Path:
    """Download one archive; e.g. ``stage_release_asset(http, root, mgsv, src, a, log)``."""
    destination = archive_path(root, game, source.mod_id, asset.file)
    status = log.begin(
        game.game_id, source.mod_id, asset.file, DOWNLOADING, RELEASE_SITE
    )
    return tracked_download(
        log, status, destination, asset.url, transport, asset.file, retry
    )


def pending_update(mod: StagedMod) -> NexusFile | None:
    """Find a newer release than the installed one; e.g. ``pending_update(mod)``."""
    if not mod.installed:
        return None
    for file in mod.files:
        current = file.category != OLD_RELEASE_CATEGORY
        if current and file.file_id not in mod.installed:
            return file
    return None
