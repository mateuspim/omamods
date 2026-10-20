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
from omamods.load_order_store import (
    apply_load_order,
    load_order_path,
    read_load_order,
)
from omamods.mod_fetch import stage_file
from omamods.nexus_config import RequestedMod, UserSettings
from omamods.asset_plans import plan_game_assets
from omamods.pak_archive import ArchiveReader, PlannedAsset
from omamods.pak_games import PakOverlayGame
from omamods.pak_storage import (
    archive_path,
    cache_downloaded_archive,
    install_pak_archive,
    revert_pak_mod,
)
from omamods.re_patch_chain import (
    fill_patch_gaps,
    number_patches,
    require_packable_chain,
)
from omamods.steam_apps import GameInspection
from omamods.ue4ss_archive import ue4ss_binaries
from omamods.ue_config import config_record, ue_config_folder


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
            f"{game.name} mods root={str(paks)!r}: expected an installed "
            f"{game.paks_subpath.as_posix()} directory"
        )
    return paks


def scanned_game_paks(game: PakOverlayGame) -> Path:
    """Locate a game found by scanning; e.g. ``scanned_game_paks(remnant2)``."""
    if game.install_root is None:
        raise ValueError(f"{game.name} install_root=None: expected a scanned game")
    paks = game.install_root / game.paks_subpath
    if not paks.is_dir():
        raise ValueError(
            f"{game.name} Paks={str(paks)!r}: expected it to still exist; rescan with r"
        )
    return paks


@dataclass(frozen=True)
class _FileInstall:
    """One staged file on its way into the game, and its ownership record."""

    game: PakOverlayGame
    paks: Path
    archive: Path
    record: Path
    file_id: int
    reader: ArchiveReader

    def write(self, root: Path, record: Path, assets: tuple[PlannedAsset, ...]) -> int:
        installed = install_pak_archive(
            self.archive, root, record, self.file_id, self.reader, assets
        )
        return len(installed)


def _install_cached(
    game: PakOverlayGame,
    settings: UserSettings,
    paks: Path,
    archive: Path,
    local: LocalArchiveRequest,
    reader: ArchiveReader,
) -> int:
    planned = plan_game_assets(reader.members(archive), game, local.option)
    if game.patch_chain is not None:
        if any(asset.packed for asset in planned):
            require_packable_chain(paks, game.patch_chain)
        planned = number_patches(planned, paks, game.patch_chain)
    root = settings.storage_root
    record = file_state_path(root, game, local.mod_id, local.file_id, local.option)
    # Keeps a container the user moved to load last under its chosen name.
    planned = apply_load_order(planned, read_load_order(load_order_path(record)))
    install = _FileInstall(game, paks, archive, record, local.file_id, reader)
    return _install_planned(install, planned)


def _install_planned(install: _FileInstall, planned: tuple[PlannedAsset, ...]) -> int:
    configs = tuple(asset for asset in planned if asset.user_config)
    files = tuple(asset for asset in planned if not asset.user_config)
    if not configs:
        return _install_game_files(install, files)
    # Prefix files go under their own record, since they have another root.
    prefix_record = config_record(install.record)
    folder = ue_config_folder(install.paks, install.game)
    count = install.write(folder, prefix_record, configs)
    try:
        return count + _install_game_files(install, files)
    except BaseException:
        revert_pak_mod(prefix_record, install.game)  # Put the game's file back.
        raise


def _install_game_files(install: _FileInstall, files: tuple[PlannedAsset, ...]) -> int:
    # UE4SS bundles go beside the executable; everything else into Paks.
    beside_exe = any(asset.beside_exe for asset in files)
    root = ue4ss_binaries(install.paks) if beside_exe else install.paks
    return install.write(root, install.record, files)


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


def _revert_records(records: tuple[Path, ...], game: PakOverlayGame) -> int:
    removed: list[Path] = []
    try:
        for record in records:
            removed.extend(revert_pak_mod(record, game))
    finally:
        # Once for all records, so reverting several variants leaves no stray
        # placeholder, and even when a later record refuses to revert.
        if game.patch_chain is not None:
            fill_patch_gaps(tuple(removed), game.patch_chain)
    return len(removed)


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
    return _revert_records(records, game)
