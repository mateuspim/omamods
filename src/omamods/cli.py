"""Compose the read-only command-line application."""

# argparse._SubParsersAction is only subscriptable at runtime from Python 3.14;
# deferred annotations keep the declared 3.12 support working.
from __future__ import annotations

import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import sys
from typing import TextIO

from omamods.filesystem import LocalFiles, ReadableFiles
from omamods.manifests import GameManifest, load_catalog
from omamods.host_cli import run_host_command
from omamods.nexus_cli import CatalogSources, NexusRuntime, run_nexus_command
from omamods.pak_games import PAK_OVERLAY_GAMES
from omamods.reporting import render_game_list, render_inspection
from omamods.steam_apps import GameInspection, inspect_game
from omamods.steam_libraries import LibraryScan, default_steam_roots, discover_libraries
from omamods.yaml_codec import ManifestDecoder, SafeYamlDecoder


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover games and install configured Nexus mods."
    )
    _global_options(parser)
    # A bare `omamods` opens the TUI, the command people run most.
    commands = parser.add_subparsers(dest="command")
    parser.set_defaults(command="tui")
    game = commands.add_parser("game", help="list games with an OmaMods manifest")
    game_commands = game.add_subparsers(dest="game_command", required=True)
    game_commands.add_parser("list", help="list catalog games and installation status")
    inspect = commands.add_parser("inspect", help="inspect one catalog game")
    inspect.add_argument("game_id", help="manifest ID, e.g. dawnwalker")
    parser.add_argument("--config", type=Path, help="private user TOML path")
    _nexus_options(commands)
    _host_options(commands)
    return parser


def _nexus_options(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    config = commands.add_parser("config", help="manage private user configuration")
    config.add_subparsers(dest="config_command", required=True).add_parser("init")
    nexus = commands.add_parser("nexus", help="download and install Nexus mods")
    nexus_commands = nexus.add_subparsers(dest="nexus_command", required=True)
    games = tuple(PAK_OVERLAY_GAMES)
    sync = nexus_commands.add_parser("sync", help="download configured mods via API")
    sync.add_argument("game_id", choices=games)
    sync.add_argument("--mod-id", type=int)
    sync.add_argument("--nxm-link", help="short-lived link from Mod Manager Download")
    sync.add_argument("--download-only", action="store_true")
    _install_options(nexus_commands, games)
    revert = nexus_commands.add_parser("revert", help="remove a mod's owned files")
    revert.add_argument("game_id", choices=games)
    revert.add_argument("mod_id", type=int)
    revert.add_argument("--file-id", type=int, help="revert only this staged file")


def _host_options(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    commands.add_parser("tui", help="browse, stage, and install mods interactively")
    nxm = commands.add_parser("nxm", help="handle Nexus 'Mod Manager Download' links")
    nxm_commands = nxm.add_subparsers(dest="nxm_command", required=True)
    nxm_commands.add_parser("register", help="make browsers send nxm links here")
    handle = nxm_commands.add_parser("handle", help="stage the file an nxm link names")
    handle.add_argument("link")


def _install_options(
    nexus_commands: argparse._SubParsersAction[argparse.ArgumentParser],
    games: tuple[str, ...],
) -> None:
    install = nexus_commands.add_parser(
        "install", help="install a manually downloaded archive; no API key needed"
    )
    install.add_argument("game_id", choices=games)
    install.add_argument("mod_id", type=int, help="number in the Nexus mod page URL")
    install.add_argument("archive", type=Path, help="downloaded .zip, .7z, or .rar")
    install.add_argument("--option", help="variant folder to install from the archive")
    install.add_argument(
        "--file-id", type=int, default=0, help="Nexus file ID, if known (default: 0)"
    )


def default_games_dir(cwd: Path) -> Path:
    """Find the catalog from anywhere; e.g. ``default_games_dir(Path.cwd())``."""
    # Browsers and app launchers start `omamods tui` outside the checkout.
    local = cwd / "games"
    if local.is_dir():
        return Path("games")
    return Path(__file__).resolve().parents[2] / "games"


def _global_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--games-dir",
        type=Path,
        default=default_games_dir(Path.cwd()),
        help="catalog directory (default: ./games, else this checkout's games/)",
    )
    parser.add_argument(
        "--steam-root",
        type=Path,
        action="append",
        help="Steam client root; repeat to replace automatic root discovery",
    )


def _select_games(
    catalog: tuple[GameManifest, ...], game_id: str | None
) -> tuple[GameManifest, ...]:
    if game_id is None:
        return catalog
    selected = tuple(game for game in catalog if game.id == game_id)
    if not selected:
        raise ValueError(
            f"game={game_id!r}: expected a catalog ID from {[game.id for game in catalog]!r}"
        )
    return selected


def _scan_roots(
    overrides: list[Path] | None, defaults: tuple[Path, ...], files: ReadableFiles
) -> LibraryScan:
    if overrides is None:
        return discover_libraries(defaults, files)
    for root in overrides:
        if not files.is_dir(root / "steamapps"):
            raise ValueError(
                f"Steam root {str(root)!r}: expected a directory containing steamapps/"
            )
    return discover_libraries(tuple(overrides), files)


def _emit_results(
    inspections: tuple[GameInspection, ...],
    scan: LibraryScan,
    command: str,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    report = (
        render_game_list(inspections)
        if command == "game"
        else render_inspection(inspections[0], scan)
    )
    print(report, file=stdout)
    return _emit_warnings(inspections, stderr)


def _emit_warnings(inspections: tuple[GameInspection, ...], stderr: TextIO) -> int:
    warnings = dict.fromkeys(
        warning for item in inspections for warning in item.warnings
    )
    for warning in warnings:
        print(f"Warning: {warning}", file=stderr)
    return 1 if warnings else 0


def run_cli(
    argv: Sequence[str],
    files: ReadableFiles,
    decoder: ManifestDecoder,
    steam_roots: tuple[Path, ...],
    stdout: TextIO,
    stderr: TextIO,
    nexus_runtime: NexusRuntime | None = None,
) -> int:
    """Run with injected I/O; e.g. ``run_cli(args, files, decoder, roots, out, err)``."""
    args = _parser().parse_args(argv)
    try:
        runtime = nexus_runtime or NexusRuntime.local(Path.home(), os.environ)
        if args.command in ("config", "nexus"):
            return run_nexus_command(args, runtime, files, decoder, steam_roots, stdout)
        if args.command in ("tui", "nxm"):
            sources = CatalogSources(files, decoder, steam_roots)
            return run_host_command(args, runtime, sources, stdout)
        catalog = load_catalog(args.games_dir, files, decoder)
        selected = _select_games(catalog, getattr(args, "game_id", None))
        scan = _scan_roots(args.steam_root, steam_roots, files)
        inspections = tuple(inspect_game(game, scan, files) for game in selected)
        return _emit_results(inspections, scan, args.command, stdout, stderr)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=stderr)
        return 2


def main() -> int:
    """Run the console entry point; for example, ``omamods inspect dawnwalker``."""
    roots = default_steam_roots(Path.home(), os.environ.get("XDG_DATA_HOME"))
    return run_cli(
        sys.argv[1:], LocalFiles(), SafeYamlDecoder(), roots, sys.stdout, sys.stderr
    )
