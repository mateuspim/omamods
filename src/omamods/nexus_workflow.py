"""Coordinate configured or manually downloaded mods with local Steam discovery."""

from dataclasses import dataclass
from pathlib import Path

from omamods.nexus_api import (
    NexusApi,
    NexusFile,
    NxmAuthorization,
    parse_nexus_page,
    select_file,
)
from omamods.install_records import (
    file_state_path,
    mod_state_records,
    recorded_file_id,
)
from omamods.mod_fetch import stage_file
from omamods.nexus_config import RequestedMod, UserSettings
from omamods.pak_archive import ArchiveReader, plan_pak_assets
from omamods.pak_games import PakOverlayGame
from omamods.pak_storage import (
    archive_path,
    cache_downloaded_archive,
    install_pak_archive,
    revert_pak_mod,
)
from omamods.steam_apps import GameInspection


@dataclass(frozen=True)
class LocalArchiveRequest:
    """An archive the user downloaded by hand, e.g. without a Nexus API key."""

    source: Path
    mod_id: int
    file_id: int
    option: str | None


@dataclass(frozen=True)
class SyncRequest:
    """Which configured mods to sync and how far to go."""

    nxm: NxmAuthorization | None
    download_only: bool
    mod_id: int | None


def _install_root(
    game: PakOverlayGame, settings: UserSettings, inspection: GameInspection
) -> Path:
    if game.game_id in settings.install_dirs:
        return settings.install_dirs[game.game_id]
    installed = tuple(
        app
        for app in inspection.installations
        if app.files_present and app.fully_installed
    )
    if len(installed) != 1:
        raise ValueError(
            f"{game.name} installations={len(installed)}: expected exactly one; "
            f"set games.{game.game_id}.install_dir"
        )
    return installed[0].install_path


def game_paks(
    game: PakOverlayGame, settings: UserSettings, inspection: GameInspection
) -> Path:
    """Locate the actual game; e.g. ``game_paks(cronos, settings, inspection)``."""
    if inspection.game.id != game.game_id:
        raise ValueError(f"game={inspection.game.id!r}: expected {game.game_id!r}")
    paks = _install_root(game, settings, inspection) / game.paks_subpath
    if not paks.is_dir():
        raise ValueError(
            f"{game.name} Paks={str(paks)!r}: expected an installed Content/Paks directory"
        )
    return paks


def _install_cached(
    game: PakOverlayGame,
    settings: UserSettings,
    paks: Path,
    archive: Path,
    local: LocalArchiveRequest,
    reader: ArchiveReader,
) -> int:
    planned = plan_pak_assets(reader.members(archive), game, local.option)
    record = file_state_path(settings.storage_root, game, local.mod_id, local.file_id)
    installed = install_pak_archive(
        archive, paks, record, local.file_id, reader, planned
    )
    return len(installed)


def install_local_archive(
    game: PakOverlayGame,
    settings: UserSettings,
    paks: Path,
    local: LocalArchiveRequest,
    reader: ArchiveReader,
) -> tuple[Path, int]:
    """Install a hand-downloaded file; e.g. ``install_local_archive(sb, cfg, paks, req, reader)``."""
    if not local.source.is_file():
        raise ValueError(
            f"archive={str(local.source)!r}: expected an existing downloaded file"
        )
    file = NexusFile(local.file_id, local.source.name, "MANUAL", 0)
    destination = archive_path(settings.storage_root, game, local.mod_id, file)
    cached = cache_downloaded_archive(destination, local.source)
    return cached, _install_cached(game, settings, paks, cached, local, reader)


def _selected_specs(
    game: PakOverlayGame, settings: UserSettings, mod_id: int | None
) -> tuple[RequestedMod, ...]:
    selected = tuple(
        spec
        for spec in settings.mods
        if spec.game == game.game_id
        and (mod_id is None or parse_nexus_page(spec.url).mod_id == mod_id)
    )
    if not selected:
        raise ValueError(
            f"configured {game.name} mod={mod_id!r}: expected at least one [[mods]] entry"
        )
    return selected


def _download_spec(
    game: PakOverlayGame,
    spec: RequestedMod,
    settings: UserSettings,
    api: NexusApi,
    nxm: NxmAuthorization | None,
) -> tuple[Path, LocalArchiveRequest]:
    page = parse_nexus_page(spec.url)
    if page.domain != game.nexus_domain:
        raise ValueError(
            f"Nexus domain={page.domain!r}: expected {game.nexus_domain!r}"
        )
    file = select_file(api.files(page), spec.file_id or (nxm.file_id if nxm else None))
    destination = stage_file(api, game, page, file, settings.storage_root, nxm)
    request = LocalArchiveRequest(destination, page.mod_id, file.file_id, spec.option)
    return destination, request


def _require_api_key(settings: UserSettings) -> None:
    if not settings.api_key:
        raise ValueError(
            "Nexus API key: expected nexus.api_key in private config or "
            "NEXUS_API_KEY; without one, use 'omamods nexus install' on a "
            "manually downloaded archive"
        )


def sync_pak_mods(
    game: PakOverlayGame,
    settings: UserSettings,
    paks: Path | None,
    api: NexusApi,
    reader: ArchiveReader,
    request: SyncRequest,
) -> tuple[tuple[Path, int], ...]:
    """Sync configured mods; e.g. ``sync_pak_mods(sb, cfg, paks, api, reader, req)``."""
    _require_api_key(settings)
    specs = _selected_specs(game, settings, request.mod_id)
    if request.nxm and len(specs) != 1:
        raise ValueError(
            f"NXM link for {len(specs)} mods: expected --mod-id to select one"
        )
    results: list[tuple[Path, int]] = []
    for spec in specs:
        archive, local = _download_spec(game, spec, settings, api, request.nxm)
        count = (
            0
            if paks is None
            else _install_cached(game, settings, paks, archive, local, reader)
        )
        results.append((archive, count))
    return tuple(results)


def revert_mod_files(
    game: PakOverlayGame, storage_root: Path, mod_id: int, file_id: int | None
) -> int:
    """Revert one file or a whole mod; e.g. ``revert_mod_files(sb, root, 1, None)``."""
    records = tuple(
        record
        for record in mod_state_records(storage_root, game, mod_id)
        if file_id is None or recorded_file_id(record) == file_id
    )
    if not records:
        folder = storage_root / "state" / game.game_id
        raise ValueError(
            f"{game.name} mod={mod_id} file={file_id!r}: expected install state in "
            f"{str(folder / f'{mod_id}.json')!r} or {str(folder / str(mod_id))!r}"
        )
    return sum(len(revert_pak_mod(record, game)) for record in records)
