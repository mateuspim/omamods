"""Compose private configuration, Nexus requests, and Unreal asset installation."""

from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, TextIO

from omamods.filesystem import ReadableFiles
from omamods.manifests import load_catalog
from omamods.nexus_api import (
    NexusApi,
    NexusTransport,
    UrlNexusTransport,
    parse_nxm_link,
)
from omamods.nexus_config import (
    ConfigFiles,
    LocalConfigFiles,
    UserSettings,
    default_config_path,
    default_storage_root,
    initialize_config,
    load_user_config,
)
from omamods.nexus_workflow import (
    LocalArchiveRequest,
    SyncRequest,
    game_paks,
    install_local_archive,
    revert_mod_files,
    sync_pak_mods,
)
from omamods.host_programs import (
    CommandRunner,
    DetachedLauncher,
    Launcher,
    SubprocessRunner,
)
from omamods.pak_archive import ArchiveReader, BsdtarArchiveReader
from omamods.pak_games import PakOverlayGame, pak_overlay_game
from omamods.steam_apps import GameInspection, inspect_game
from omamods.steam_libraries import discover_libraries
from omamods.yaml_codec import ManifestDecoder


@dataclass(frozen=True)
class NexusRuntime:
    """Inject host paths and external I/O for repeatable command tests."""

    home: Path
    environment: Mapping[str, str]
    config_files: ConfigFiles
    transport: NexusTransport
    archive_reader: ArchiveReader
    runner: CommandRunner = field(default_factory=SubprocessRunner)
    launcher: Launcher = field(default_factory=DetachedLauncher)

    @classmethod
    def local(cls, home: Path, environment: Mapping[str, str]) -> "NexusRuntime":
        """Compose host adapters; e.g. ``NexusRuntime.local(Path.home(), os.environ)``."""
        return cls(
            home,
            environment,
            LocalConfigFiles(),
            UrlNexusTransport(),
            BsdtarArchiveReader(),
        )


def config_paths(args: Namespace, runtime: NexusRuntime) -> tuple[Path, Path]:
    path = args.config or default_config_path(
        runtime.home, runtime.environment.get("XDG_CONFIG_HOME")
    )
    root = default_storage_root(runtime.home, runtime.environment.get("XDG_DATA_HOME"))
    return path, root


@dataclass(frozen=True)
class CatalogSources:
    """Read-only inputs used to locate the game on disk."""

    files: ReadableFiles
    decoder: ManifestDecoder
    steam_roots: tuple[Path, ...]


def game_inspection(
    args: Namespace, game: PakOverlayGame, sources: CatalogSources
) -> GameInspection:
    catalog = load_catalog(args.games_dir, sources.files, sources.decoder)
    manifest = next((item for item in catalog if item.id == game.game_id), None)
    if manifest is None:
        raise ValueError(f"game={game.game_id!r}: expected a catalog manifest")
    roots = tuple(args.steam_root) if args.steam_root else sources.steam_roots
    libraries = discover_libraries(roots, sources.files)
    return inspect_game(manifest, libraries, sources.files)


def _settings(
    args: Namespace, runtime: NexusRuntime, path: Path, fallback_root: Path
) -> UserSettings:
    try:
        return load_user_config(
            path,
            fallback_root,
            runtime.environment.get("NEXUS_API_KEY"),
            runtime.config_files,
        )
    except ValueError as error:
        # Manual installs and reverts need no API key, so a missing config is fine.
        missing = isinstance(error.__cause__, FileNotFoundError)
        if args.nexus_command == "sync" or not missing:
            raise
        return UserSettings("", fallback_root, {}, ())


def _run_sync(
    args: Namespace,
    game: PakOverlayGame,
    settings: UserSettings,
    runtime: NexusRuntime,
    sources: CatalogSources,
) -> tuple[tuple[Path, int], ...]:
    paks = None
    if not args.download_only:
        paks = game_paks(game, settings, game_inspection(args, game, sources))
    nxm = parse_nxm_link(args.nxm_link) if args.nxm_link else None
    request = SyncRequest(nxm, args.download_only, args.mod_id)
    api = NexusApi(runtime.transport, settings.api_key)
    return sync_pak_mods(game, settings, paks, api, runtime.archive_reader, request)


def _run_install(
    args: Namespace,
    game: PakOverlayGame,
    settings: UserSettings,
    runtime: NexusRuntime,
    sources: CatalogSources,
) -> tuple[tuple[Path, int], ...]:
    paks = game_paks(game, settings, game_inspection(args, game, sources))
    local = LocalArchiveRequest(
        args.archive.expanduser().absolute(), args.mod_id, args.file_id, args.option
    )
    return (install_local_archive(game, settings, paks, local, runtime.archive_reader),)


def run_nexus_command(
    args: Namespace,
    runtime: NexusRuntime,
    files: ReadableFiles,
    decoder: ManifestDecoder,
    steam_roots: tuple[Path, ...],
    stdout: TextIO,
) -> int:
    """Run a Nexus action; e.g. ``run_nexus_command(args, runtime, fs, yaml, roots, out)``."""
    path, fallback_root = config_paths(args, runtime)
    if args.command == "config":
        initialize_config(path, fallback_root, runtime.config_files)
        print(f"Created private config: {path}", file=stdout)
        return 0
    game = pak_overlay_game(args.game_id)
    settings = _settings(args, runtime, path, fallback_root)
    if args.nexus_command == "revert":
        count = revert_mod_files(game, settings.storage_root, args.mod_id, args.file_id)
        print(f"Reverted {game.name} mod {args.mod_id}: {count} files", file=stdout)
        return 0
    sources = CatalogSources(files, decoder, steam_roots)
    run = _run_sync if args.nexus_command == "sync" else _run_install
    for archive, installed in run(args, game, settings, runtime, sources):
        print(f"Archive: {archive}; installed files: {installed}", file=stdout)
    return 0
