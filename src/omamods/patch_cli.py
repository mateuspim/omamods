"""Run ``omamods patch apply|revert|status`` for built-in executable patches."""

# argparse._SubParsersAction is only subscriptable at runtime from Python 3.14.
from __future__ import annotations

import argparse
from pathlib import Path
from typing import TextIO

from omamods.exe_patch_games import EXE_PATCH_GAMES, ExePatchGame, exe_patch_game
from omamods.exe_patch_install import (
    ExePatchTarget,
    apply_exe_patch,
    describe_patch_state,
    revert_exe_patch,
)
from omamods.manifests import load_catalog
from omamods.nexus_cli import CatalogSources, NexusRuntime, config_paths
from omamods.nexus_config import load_user_config
from omamods.steam_apps import inspect_game
from omamods.steam_libraries import discover_libraries


def add_patch_commands(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the parser; e.g. ``add_patch_commands(subparsers)``."""
    patch = commands.add_parser("patch", help="patch or restore a game executable")
    actions = patch.add_subparsers(dest="patch_command", required=True)
    games = tuple(EXE_PATCH_GAMES)
    apply = actions.add_parser("apply", help="back up the exe and patch it")
    apply.add_argument("game_id", choices=games)
    apply.add_argument("--resolution", required=True, help="e.g. 3440x1440")
    for name, text in (("revert", "restore the original exe"), ("status", "show it")):
        actions.add_parser(name, help=text).add_argument("game_id", choices=games)


def _storage_root(args: argparse.Namespace, runtime: NexusRuntime) -> Path:
    path, fallback = config_paths(args, runtime)
    try:
        return load_user_config(path, fallback, None, runtime.config_files).storage_root
    except ValueError as error:
        # Patching needs no Nexus key, so a missing config means the default root.
        if isinstance(error.__cause__, FileNotFoundError):
            return fallback
        raise


def _game_exe(
    args: argparse.Namespace, game: ExePatchGame, sources: CatalogSources
) -> Path:
    catalog = load_catalog(args.games_dir, sources.files, sources.decoder)
    manifest = next((item for item in catalog if item.id == game.game_id), None)
    if manifest is None:
        raise ValueError(f"game={game.game_id!r}: expected a catalog manifest")
    roots = tuple(args.steam_root) if args.steam_root else sources.steam_roots
    inspection = inspect_game(
        manifest, discover_libraries(roots, sources.files), sources.files
    )
    for app in inspection.installations:
        if app.files_present and (app.install_path / game.exe_name).is_file():
            return app.install_path / game.exe_name
    raise ValueError(f"{game.name}: expected an installed {game.exe_name} in Steam")


def run_patch_command(
    args: argparse.Namespace,
    runtime: NexusRuntime,
    sources: CatalogSources,
    stdout: TextIO,
) -> int:
    """Apply, revert, or report; e.g. ``run_patch_command(args, runtime, sources, out)``."""
    game = exe_patch_game(args.game_id)
    exe = _game_exe(args, game, sources)
    target = ExePatchTarget.for_game(_storage_root(args, runtime), game.game_id, exe)
    if args.patch_command == "status":
        print(describe_patch_state(target), file=stdout)
    elif args.patch_command == "revert":
        print(revert_exe_patch(target), file=stdout)
    else:
        _apply(game, target, args.resolution, stdout)
    return 0


def _apply(
    game: ExePatchGame, target: ExePatchTarget, option: str, stdout: TextIO
) -> None:
    original = target.exe.read_bytes()
    patched = game.build(original, option)
    apply_exe_patch(target, original, patched, game.describe(option))
    print(f"{target.exe.name}: patched for {option}", file=stdout)
    print(f"Original kept in {target.backup}", file=stdout)
