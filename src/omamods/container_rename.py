"""Rename one installed Unreal container's files together and keep its record true.

A rename leaves the bytes alone, so only each asset's ``relative_path`` in the
ownership record changes; revert then finds and removes the renamed files.
"""

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import tempfile

from omamods.pak_archive import ASSET_SUFFIXES
from omamods.pak_games import PakOverlayGame
from omamods.pak_storage import (
    InstalledAsset,
    file_sha256,
    owned_target,
    read_ownership,
)

Move = Callable[[Path, Path], None]


@dataclass(frozen=True)
class FileMove:
    """One owned file's old and new path, relative to Paks."""

    old: str
    new: str


def require_unreal_paks(game: PakOverlayGame) -> None:
    """Refuse games without Unreal pak order; e.g. ``require_unreal_paks(mgs)``."""
    if game.patch_chain is not None or game.redengine or game.asi_loader:
        raise ValueError(
            f"game={game.game_id!r}: expected an Unreal game that loads "
            f"{game.mods_dirname}/ paks by name"
        )


def _stem_of(relative: str) -> str | None:
    pure = PurePosixPath(relative)
    if pure.suffix.lower() not in ASSET_SUFFIXES:
        return None
    return pure.with_suffix("").as_posix()


def _require_sibling(old_stem: str, new_stem: str) -> None:
    old, new = PurePosixPath(old_stem), PurePosixPath(new_stem)
    if new.parent != old.parent or new.name in ("", ".", "..") or old == new:
        raise ValueError(
            f"new container={new_stem!r}: expected another name in "
            f"{old.parent.as_posix()!r} than {old_stem!r}"
        )


def container_moves(
    record: Path, game: PakOverlayGame, old_stem: str, new_stem: str
) -> tuple[FileMove, ...]:
    """List the renames, without checking the game folder.

    Example: ``container_moves(state, mgs, '~mods/Fix_P', '~mods/Fix_1_P')``.
    """
    require_unreal_paks(game)
    _require_sibling(old_stem, new_stem)
    _, assets = read_ownership(record, game)
    moves = tuple(
        FileMove(a.relative_path, new_stem + PurePosixPath(a.relative_path).suffix)
        for a in assets
        if _stem_of(a.relative_path) == old_stem
    )
    if not moves:
        raise ValueError(
            f"container={old_stem!r}: expected files of it in {str(record)!r}"
        )
    return moves


def _preflight(
    paks: Path, assets: tuple[InstalledAsset, ...], moves: tuple[FileMove, ...]
) -> None:
    digests = {asset.relative_path: asset.sha256 for asset in assets}
    for move in moves:
        old, new = owned_target(paks, move.old), owned_target(paks, move.new)
        if not old.is_file() or file_sha256(old) != digests[move.old]:
            raise ValueError(
                f"owned file={str(old)!r}: expected it present with its recorded "
                "SHA-256; reinstall the mod first"
            )
        if new.exists() or new.is_symlink():
            raise ValueError(
                f"rename target={str(new)!r}: expected no file there; another mod "
                "or a manual copy already uses that name"
            )


def _rewrite_record(record: Path, moves: tuple[FileMove, ...]) -> None:
    state = json.loads(record.read_text(encoding="utf-8"))
    renamed = {move.old: move.new for move in moves}
    for asset in state["assets"]:
        path = asset["relative_path"]
        asset["relative_path"] = renamed.get(path, path)
    with tempfile.NamedTemporaryFile(
        "w", dir=record.parent, prefix=".", delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(state, stream, indent=2)
    try:
        os.replace(temporary, record)
    finally:
        temporary.unlink(missing_ok=True)


def _move_all(paks: Path, moves: tuple[FileMove, ...], move: Move) -> list[FileMove]:
    done: list[FileMove] = []
    try:
        for step in moves:
            move(paks / step.old, paks / step.new)
            done.append(step)
    except BaseException:
        _move_back(paks, done, move)
        raise
    return done


def _move_back(paks: Path, done: list[FileMove], move: Move) -> None:
    for step in reversed(done):
        move(paks / step.new, paks / step.old)


def rename_container(
    record: Path,
    game: PakOverlayGame,
    old_stem: str,
    new_stem: str,
    move: Move = os.rename,
) -> tuple[FileMove, ...]:
    """Rename a container's files and record, or change nothing on failure.

    Example: ``rename_container(state, mgs, '~mods/Fix_P', '~mods/Fix_1_P')``.
    """
    moves = container_moves(record, game, old_stem, new_stem)
    paks, assets = read_ownership(record, game)
    _preflight(paks, assets, moves)
    done = _move_all(paks, moves, move)
    try:
        _rewrite_record(record, moves)
    except BaseException:
        _move_back(paks, done, move)
        raise
    return moves
