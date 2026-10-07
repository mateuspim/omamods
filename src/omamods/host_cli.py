"""Compose the TUI and the browser's nxm handler from host adapters."""

from argparse import Namespace
from pathlib import Path
import shutil
import sys
from typing import Mapping, TextIO

from omamods.browser_windows import chromium_browser
from omamods.nexus_api import NexusApi
from omamods.nexus_cli import (
    CatalogSources,
    NexusRuntime,
    config_paths,
    game_inspection,
)
from omamods.nexus_config import UserSettings, load_user_config
from omamods.nexus_workflow import game_paks
from omamods.nxm_handler import handle_nxm_click
from omamods.game_shelf import GameShelf, ShelfSources, scan_shelf
from omamods.heroic_games import default_heroic_roots
from omamods.manifests import GameManifest, load_catalog
from omamods.pak_games import PAK_OVERLAY_GAMES, PakOverlayGame
from omamods.tui.service import ModsService, TuiHost


def omamods_executable(argv0: str) -> Path:
    """Find the command browsers should run; e.g. ``omamods_executable(sys.argv[0])``."""
    invoked = Path(argv0)
    if invoked.name == "omamods" and invoked.is_file():
        return invoked.absolute()
    found = shutil.which("omamods")
    if found is None:
        raise ValueError(
            f"argv0={argv0!r}: expected the installed 'omamods' script; "
            "run 'pip install -e .' and start it as 'omamods'"
        )
    return Path(found).absolute()


class SteamPaksLocator:
    """Find a game's Paks folder from config or Steam; e.g. ``locator(sb, settings)``."""

    def __init__(self, args: Namespace, sources: CatalogSources) -> None:
        self.args = args
        self.sources = sources

    def __call__(self, game: PakOverlayGame, settings: UserSettings) -> Path:
        inspection = game_inspection(self.args, game, self.sources)
        return game_paks(game, settings, inspection)


class HostShelfScanner:
    """Scan Steam and Heroic for the home screen; e.g. ``scanner().entries``."""

    def __init__(
        self, args: Namespace, sources: CatalogSources, runtime: NexusRuntime
    ) -> None:
        self.args = args
        self.sources = sources
        self.runtime = runtime

    def _catalog(self) -> tuple[GameManifest, ...]:
        sources = self.sources
        return load_catalog(self.args.games_dir, sources.files, sources.decoder)

    def __call__(self) -> GameShelf:
        args, runtime = self.args, self.runtime
        config_home = runtime.environment.get("XDG_CONFIG_HOME")
        shelf_sources = ShelfSources(
            self._catalog,
            tuple(args.steam_root) if args.steam_root else self.sources.steam_roots,
            default_heroic_roots(runtime.home, config_home),
            self.sources.files,
            frozenset(PAK_OVERLAY_GAMES),
        )
        return scan_shelf(shelf_sources)


def data_dirs(environment: Mapping[str, str], home: Path) -> tuple[Path, ...]:
    """List XDG data folders in lookup order; e.g. ``data_dirs(os.environ, home)``."""
    user = Path(environment.get("XDG_DATA_HOME") or home / ".local/share")
    system = environment.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return (user, *(Path(item) for item in system.split(":") if item))


def tui_host(
    args: Namespace, runtime: NexusRuntime, sources: CatalogSources
) -> TuiHost:
    """Wire host I/O for the TUI; e.g. ``tui_host(args, runtime, sources)``."""
    path, fallback_root = config_paths(args, runtime)
    data_home = runtime.environment.get("XDG_DATA_HOME")
    applications = Path(data_home or runtime.home / ".local/share") / "applications"
    return TuiHost(
        path,
        fallback_root,
        runtime.environment,
        runtime.config_files,
        runtime.transport,
        runtime.archive_reader,
        runtime.runner,
        runtime.launcher,
        SteamPaksLocator(args, sources),
        omamods_executable(sys.argv[0]),
        applications,
        HostShelfScanner(args, sources, runtime),
        chromium_browser(runtime.runner, data_dirs(runtime.environment, runtime.home)),
    )


def _handle_nxm(args: Namespace, runtime: NexusRuntime, stdout: TextIO) -> int:
    path, fallback_root = config_paths(args, runtime)
    settings = load_user_config(
        path,
        fallback_root,
        runtime.environment.get("NEXUS_API_KEY"),
        runtime.config_files,
    )
    api = NexusApi(runtime.transport, settings.api_key)
    code = handle_nxm_click(args.link, api, settings.storage_root, runtime.runner)
    print("Staged" if code == 0 else "Failed; see logs/nxm.jsonl", file=stdout)
    return code


def run_host_command(
    args: Namespace, runtime: NexusRuntime, sources: CatalogSources, stdout: TextIO
) -> int:
    """Run tui or nxm commands; e.g. ``run_host_command(args, runtime, sources, out)``."""
    if args.command == "nxm" and args.nxm_command == "handle":
        return _handle_nxm(args, runtime, stdout)
    service = ModsService(tui_host(args, runtime, sources))
    if args.command == "nxm":
        registration = service.register_nxm()
        print(f"Registered {registration.desktop_file}", file=stdout)
        return 0
    from omamods.tui.app import OmaModsApp  # Keep Textual out of plain CLI runs.

    OmaModsApp(service).run()
    return 0
