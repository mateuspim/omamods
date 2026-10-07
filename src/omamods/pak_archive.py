"""Map only self-contained Unreal asset files from a Nexus archive into Paks."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from typing import BinaryIO, Protocol

from omamods.pak_games import IOSTORE_SUFFIXES, PakOverlayGame

ASSET_SUFFIXES = IOSTORE_SUFFIXES
LOADER_SUFFIXES = frozenset({".asi", ".dll", ".exe", ".lua"})
LOADER_DIRECTORIES = frozenset({"binaries", "ue4ss"})
ArchiveAsset = tuple[str, PurePosixPath]


@dataclass(frozen=True)
class PlannedAsset:
    """One archive member and its safe game-relative destination."""

    member: str
    target: Path


class ArchiveReader(Protocol):
    """Keep archive tooling behind an injectable interface."""

    def members(self, archive: Path) -> tuple[str, ...]:
        """List members; for example, ``reader.members(archive)``."""
        ...

    def copy_member(self, archive: Path, member: str, destination: BinaryIO) -> None:
        """Read one member; for example, ``reader.copy_member(zip, name, file)``."""
        ...


class BsdtarArchiveReader:
    """Read ZIP, 7z, and RAR archives through the host's libarchive tool."""

    def members(self, archive: Path) -> tuple[str, ...]:
        """List without unpacking; for example, ``reader.members(archive)``."""
        result = subprocess.run(
            ("bsdtar", "-tf", str(archive)), capture_output=True, text=True, check=False
        )
        if result.returncode:
            raise ValueError(f"archive={str(archive)!r}: expected a readable archive")
        return tuple(result.stdout.splitlines())

    def copy_member(self, archive: Path, member: str, destination: BinaryIO) -> None:
        """Stream one asset; for example, ``reader.copy_member(zip, name, file)``."""
        process = subprocess.Popen(
            ("bsdtar", "-xOf", str(archive), member),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        assert process.stdout is not None
        with process.stdout:
            shutil.copyfileobj(process.stdout, destination)
        if process.wait():
            raise ValueError(f"archive member={member!r}: expected a readable file")


def _member_path(member: str) -> PurePosixPath:
    if not member or "\\" in member or "\0" in member or member.startswith("/"):
        raise ValueError(f"archive member={member!r}: expected a relative POSIX path")
    if any(part in ("..", ".") for part in member.split("/")):
        raise ValueError(f"archive member={member!r}: expected no traversal components")
    return PurePosixPath(member)


def _reject_loader(member: str, path: PurePosixPath) -> None:
    # Installing only the paks of a loader-dependent mod yields a broken game
    # state, so refuse the whole archive (e.g. Stellar Blade mod 524).
    directories = {part.lower() for part in path.parts}
    if path.suffix.lower() in LOADER_SUFFIXES or directories & LOADER_DIRECTORIES:
        raise ValueError(
            f"archive member={member!r}: expected only self-contained "
            ".pak/.utoc/.ucas assets; loaders and scripts need another adapter"
        )


def _asset_members(members: tuple[str, ...]) -> tuple[ArchiveAsset, ...]:
    assets: list[ArchiveAsset] = []
    for member in members:
        path = _member_path(member)
        _reject_loader(member, path)
        if path.suffix.lower() in ASSET_SUFFIXES:
            assets.append((member, path))
    return tuple(assets)


def _variant_folders(assets: tuple[ArchiveAsset, ...]) -> list[str]:
    return sorted({path.parent.as_posix() for _, path in assets})


def _in_option(path: PurePosixPath, option: str) -> bool:
    return option in path.parent.parts or path.parent.as_posix() == option


def _select_option(
    assets: tuple[ArchiveAsset, ...], option: str | None
) -> tuple[ArchiveAsset, ...]:
    if option is None:
        return assets
    chosen = tuple(asset for asset in assets if _in_option(asset[1], option))
    if not chosen:
        raise ValueError(
            f"option={option!r}: expected a folder from {_variant_folders(assets)!r}"
        )
    return chosen


def _anchored_target(path: PurePosixPath, mods_dirname: str) -> Path | None:
    folders = [part.lower() for part in path.parts[:-1]]
    if mods_dirname.lower() not in folders:
        return None
    tail = path.parts[folders.index(mods_dirname.lower()) + 1 :]
    return Path(mods_dirname, *tail)


def _anchored_assets(
    assets: tuple[ArchiveAsset, ...], game: PakOverlayGame
) -> tuple[PlannedAsset, ...]:
    planned = (
        (member, _anchored_target(path, game.mods_dirname)) for member, path in assets
    )
    return tuple(PlannedAsset(member, target) for member, target in planned if target)


def _flat_assets(
    assets: tuple[ArchiveAsset, ...], game: PakOverlayGame
) -> tuple[PlannedAsset, ...]:
    paths = tuple(path for _, path in assets)
    suffixes = frozenset(path.suffix.lower() for path in paths)
    if (
        len({path.stem for path in paths}) != 1
        or len(suffixes) != len(paths)
        or suffixes not in game.flat_suffix_sets
    ):
        shapes = " or ".join("/".join(sorted(s)) for s in game.flat_suffix_sets)
        raise ValueError(
            f"{game.name} archive root={[str(p) for p in paths]!r}: "
            f"expected one same-stem {shapes} set"
        )
    return tuple(
        PlannedAsset(member, Path(game.mods_dirname, path.name))
        for member, path in assets
    )


def _folder_assets(
    assets: tuple[ArchiveAsset, ...], game: PakOverlayGame
) -> tuple[PlannedAsset, ...]:
    folders = _variant_folders(assets)
    if folders == ["."]:
        return _flat_assets(assets, game)
    if len(folders) > 1:
        raise ValueError(
            f"{game.name} archive folders={folders!r}: expected one variant; "
            "set option in the [[mods]] entry"
        )
    # Authors ask for the option folder to be copied intact (Stellar Blade mod 3477).
    return tuple(
        PlannedAsset(member, Path(game.mods_dirname, path.parent.name, path.name))
        for member, path in assets
    )


def _require_unique_pak(
    planned: tuple[PlannedAsset, ...], game: PakOverlayGame
) -> None:
    targets = [asset.target for asset in planned]
    for target in targets:
        if targets.count(target) > 1:
            raise ValueError(
                f"asset target={str(target)!r}: expected one archive member per path"
            )
    if not any(target.suffix.lower() == ".pak" for target in targets):
        raise ValueError(f"{game.name} archive: expected at least one .pak asset")


def plan_pak_assets(
    members: tuple[str, ...], game: PakOverlayGame, option: str | None
) -> tuple[PlannedAsset, ...]:
    """Constrain paths; e.g. ``plan_pak_assets(('Mods/a.pak',), cronos, None)``."""
    assets = _select_option(_asset_members(members), option)
    if not assets:
        raise ValueError(
            f"{game.name} archive members={list(members)!r}: expected .pak assets"
        )
    planned = _anchored_assets(assets, game) or _folder_assets(assets, game)
    _require_unique_pak(planned, game)
    return planned


def variant_folders(members: tuple[str, ...], game: PakOverlayGame) -> tuple[str, ...]:
    """List choosable variants (empty if none); e.g. ``variant_folders(names, sb)``."""
    assets = _asset_members(members)
    if _anchored_assets(assets, game):
        return ()
    folders = _variant_folders(assets)
    return tuple(folders) if len(folders) > 1 else ()
