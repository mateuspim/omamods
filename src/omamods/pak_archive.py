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
    # True when the install renames the file to the next free patch number of
    # an RE Engine game; until then the target holds the archive's file name.
    next_patch: bool = False
    # Loose (archive member, natives/... path) pairs packed into this one pak.
    packed: tuple[tuple[str, str], ...] = ()
    # True when the target is an empty RE Engine patch (Capcom's 0-byte ones
    # or a placeholder) that the install may overwrite and revert restores.
    replaces_empty: bool = False
    # An empty pak means a broken extraction, but Cyberpunk frameworks ship
    # 0-byte marker files (ArchiveXL's r6/config/redsUserHints/ArchiveXL.toml).
    allow_empty: bool = False
    # A settings file the mod rewrites at run time (UE4SS Lua configs); revert
    # removes it even when it no longer matches the archive.
    user_editable: bool = False
    # The target is relative to the folder holding the game's executable
    # (UE4SS bundles) instead of Paks.
    beside_exe: bool = False
    # The target is relative to the game's Saved/Config folder in the Proton
    # prefix (a bundle's Engine.ini); the install sets the game's file aside.
    user_config: bool = False


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


def archive_member_path(member: str) -> PurePosixPath:
    """Refuse unsafe names; e.g. ``archive_member_path('Mods/a.pak')``."""
    if not member or "\\" in member or "\0" in member or member.startswith("/"):
        raise ValueError(f"archive member={member!r}: expected a relative POSIX path")
    if any(part in ("..", ".") for part in member.split("/")):
        raise ValueError(f"archive member={member!r}: expected no traversal components")
    return PurePosixPath(member)


def reject_loader(member: str, path: PurePosixPath) -> None:
    """Refuse script loaders; e.g. ``reject_loader(name, PurePosixPath(name))``."""
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
        path = archive_member_path(member)
        reject_loader(member, path)
        if path.suffix.lower() in ASSET_SUFFIXES:
            assets.append((member, path))
    return tuple(assets)


def asset_folders(assets: tuple[ArchiveAsset, ...]) -> list[str]:
    """List folders holding assets; e.g. ``asset_folders(assets) == ['.']``."""
    return sorted({path.parent.as_posix() for _, path in assets})


def _in_option(path: PurePosixPath, option: str) -> bool:
    return option in path.parent.parts or path.parent.as_posix() == option


def _is_shared_with(path: PurePosixPath, folders: set[PurePosixPath]) -> bool:
    return any(path.parent in folder.parents for folder in folders)


def select_variant(
    assets: tuple[ArchiveAsset, ...], option: str | None
) -> tuple[ArchiveAsset, ...]:
    """Keep one variant folder and the folders above it; e.g. ``select_variant(assets, 'Black')``."""
    if option is None:
        return assets
    chosen = tuple(asset for asset in assets if _in_option(asset[1], option))
    if not chosen:
        raise ValueError(
            f"option={option!r}: expected a folder from {asset_folders(assets)!r}"
        )
    # Paks beside the variant folders are shared parts every variant needs,
    # e.g. a Clair Obscur outfit mod's 'hero/Hero_Addons_P'.
    folders = {path.parent for _, path in chosen}
    return tuple(
        asset
        for asset in assets
        if asset in chosen or _is_shared_with(asset[1], folders)
    )


def _common_folder(folders: list[PurePosixPath]) -> PurePosixPath:
    common = folders[0]
    for folder in folders[1:]:
        while common != folder and common not in folder.parents:
            common = common.parent
    return common


def variant_base(assets: tuple[ArchiveAsset, ...]) -> PurePosixPath:
    """Find the folder variant paths are kept below; e.g. ``variant_base(assets)``."""
    folders = sorted({path.parent for _, path in assets})
    common = _common_folder(folders)
    # Keep a lone folder's own name, as authors ask (Stellar Blade mod 3477).
    return common.parent if common in folders else common


def _single_variant_chain(folders: list[PurePosixPath], game: PakOverlayGame) -> None:
    deepest = max(folders, key=lambda folder: len(folder.parts))
    if all(folder == deepest or folder in deepest.parents for folder in folders):
        return
    raise ValueError(
        f"{game.name} archive folders={[f.as_posix() for f in folders]!r}: "
        "expected one variant; set option in the [[mods]] entry"
    )


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


def _incomplete_stems(
    paths: tuple[PurePosixPath, ...], game: PakOverlayGame
) -> list[str]:
    suffixes: dict[str, list[str]] = {}
    for path in paths:
        suffixes.setdefault(path.stem, []).append(path.suffix.lower())
    return sorted(
        stem
        for stem, found in suffixes.items()
        if len(set(found)) != len(found)
        or frozenset(found) not in game.flat_suffix_sets
    )


def _flat_assets(
    assets: tuple[ArchiveAsset, ...], game: PakOverlayGame
) -> tuple[PlannedAsset, ...]:
    paths = tuple(path for _, path in assets)
    # Packs may ship several loose sets, one per outfit (a Stellar Blade outfit pack).
    incomplete = _incomplete_stems(paths, game)
    if incomplete:
        shapes = " or ".join("/".join(sorted(s)) for s in game.flat_suffix_sets)
        raise ValueError(
            f"{game.name} archive root={[str(p) for p in paths]!r}: "
            f"expected each same-stem group to be a {shapes} set; "
            f"incomplete: {incomplete!r}"
        )
    return tuple(
        PlannedAsset(member, Path(game.mods_dirname, path.name))
        for member, path in assets
    )


def _folder_assets(
    assets: tuple[ArchiveAsset, ...], game: PakOverlayGame, base: PurePosixPath
) -> tuple[PlannedAsset, ...]:
    if asset_folders(assets) == ["."]:
        return _flat_assets(assets, game)
    _single_variant_chain(sorted({path.parent for _, path in assets}), game)
    # Authors ask for the option folder to be copied intact (Stellar Blade mod
    # 3477). Keeping the path below the base also keeps same-named folders of
    # different variants apart ('hero/armor/black' vs 'knight/armor/black').
    return tuple(
        PlannedAsset(member, Path(game.mods_dirname, *path.relative_to(base).parts))
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
    every_asset = _asset_members(members)
    if not every_asset:
        raise ValueError(
            f"{game.name} archive members={list(members)!r}: expected .pak assets"
        )
    assets = select_variant(every_asset, option)
    planned = _anchored_assets(assets, game) or _folder_assets(
        assets, game, variant_base(every_asset)
    )
    _require_unique_pak(planned, game)
    return planned


def _innermost(folders: list[str]) -> tuple[str, ...]:
    paths = [PurePosixPath(folder) for folder in folders]
    return tuple(
        folder.as_posix()
        for folder in paths
        if not any(folder in other.parents for other in paths)
    )


def variant_folders(members: tuple[str, ...], game: PakOverlayGame) -> tuple[str, ...]:
    """List choosable variants (empty if none); e.g. ``variant_folders(names, sb)``."""
    assets = _asset_members(members)
    if _anchored_assets(assets, game):
        return ()
    # Folders above other variants hold shared paks installed with each one.
    folders = _innermost(asset_folders(assets))
    return folders if len(folders) > 1 else ()
