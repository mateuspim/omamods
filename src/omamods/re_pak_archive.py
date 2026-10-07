"""Map an RE Engine mod archive to patch paks; refuse script loaders.

Ready-made .pak files each take a patch slot. Loose natives/ files, the
Fluffy Mod Manager format, are packed into one new pak, as Fluffy does.
"""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from omamods.pak_archive import (
    ArchiveReader,
    PlannedAsset,
    archive_member_path,
    reject_loader,
)
from omamods.pak_games import PakOverlayGame
from omamods.re_pak_writer import MemberCopier, write_re_pak

# REFramework is a dinput8.dll loader; its scripts live in reframework/.
RE_LOADER_DIRECTORIES = frozenset({"reframework"})
NATIVES = "natives"
PACKED_NAME = "natives.pak"


@dataclass(frozen=True)
class ModFile:
    """One usable archive member and the variant folder it belongs to."""

    member: str
    path: PurePosixPath
    root: str
    # Path inside the packed pak for natives/ files; None for ready-made paks.
    natives_path: str | None


def _natives_index(path: PurePosixPath) -> int | None:
    folders = [part.lower() for part in path.parts[:-1]]
    return folders.index(NATIVES) if NATIVES in folders else None


def _reject_re_loader(member: str, path: PurePosixPath) -> None:
    reject_loader(member, path)
    if {part.lower() for part in path.parts[:-1]} & RE_LOADER_DIRECTORIES:
        raise ValueError(
            f"archive member={member!r}: expected .pak or natives/ files; "
            "REFramework scripts need another adapter"
        )


def _folder_names(members: tuple[str, ...]) -> frozenset[str]:
    # bsdtar lists RAR folders without a trailing slash (Nexus RE7 mod 155),
    # so a member is a folder when other members sit beneath it.
    parents = (PurePosixPath(m.rstrip("/")).parents for m in members)
    folders = {p.as_posix() for found in parents for p in found}
    return frozenset(folders | {m.rstrip("/") for m in members if m.endswith("/")})


def _mod_file(member: str, folders: frozenset[str]) -> ModFile | None:
    path = archive_member_path(member.rstrip("/"))
    _reject_re_loader(member, path)
    index = _natives_index(path)
    if index is not None and path.as_posix() not in folders:
        root = PurePosixPath(*path.parts[:index]).as_posix()
        return ModFile(member, path, root, "/".join(path.parts[index:]))
    if index is None and path.suffix.lower() == ".pak":
        return ModFile(member, path, path.parent.as_posix(), None)
    return None  # Folders, modinfo.ini, screenshots, and readmes.


def mod_files(members: tuple[str, ...]) -> tuple[ModFile, ...]:
    """Keep paks and natives/ files; e.g. ``mod_files(('Mod/natives/stm/a.tex',))``."""
    folders = _folder_names(members)
    found = (_mod_file(member, folders) for member in members)
    usable = (file for file in found if file is not None)
    return tuple(sorted(usable, key=lambda file: file.path.as_posix()))


def _variant_roots(files: tuple[ModFile, ...]) -> list[str]:
    return sorted({file.root for file in files})


def _in_root(root: str, option: str) -> bool:
    return root == option or option in PurePosixPath(root).parts


def _chosen(
    files: tuple[ModFile, ...], option: str | None, game: PakOverlayGame
) -> tuple[ModFile, ...]:
    roots = _variant_roots(files)
    if option is None and len(roots) > 1:
        raise ValueError(
            f"{game.name} archive folders={roots!r}: expected one variant; pick one"
        )
    chosen = tuple(f for f in files if option is None or _in_root(f.root, option))
    if not chosen:
        raise ValueError(f"option={option!r}: expected a folder from {roots!r}")
    return chosen


def _packed_pak(files: tuple[ModFile, ...]) -> tuple[PlannedAsset, ...]:
    pairs = tuple((f.member, f.natives_path) for f in files if f.natives_path)
    folded = [path.lower() for _, path in pairs]
    duplicates = sorted({path for path in folded if folded.count(path) > 1})
    if duplicates:
        raise ValueError(
            f"natives paths={duplicates!r}: expected each once, ignoring case"
        )
    if not pairs:
        return ()
    return (PlannedAsset(NATIVES, Path(PACKED_NAME), next_patch=True, packed=pairs),)


def plan_patch_paks(
    members: tuple[str, ...], game: PakOverlayGame, option: str | None
) -> tuple[PlannedAsset, ...]:
    """Queue paks for patch slots; e.g. ``plan_patch_paks(('Mod/a.pak',), re7, None)``."""
    files = mod_files(members)
    if not files:
        raise ValueError(
            f"{game.name} archive members={list(members)!r}: expected .pak "
            "patches or natives/ files"
        )
    chosen = _chosen(files, option, game)
    # Install numbers the paks; until then each target keeps the file's name.
    ready = tuple(
        PlannedAsset(f.member, Path(f.path.name), next_patch=True)
        for f in chosen
        if f.natives_path is None
    )
    return ready + _packed_pak(chosen)


def patch_pak_variants(members: tuple[str, ...]) -> tuple[str, ...]:
    """List choosable variants (empty if none); e.g. ``patch_pak_variants(names)``."""
    roots = _variant_roots(mod_files(members))
    return tuple(roots) if len(roots) > 1 else ()


def write_packed_pak(
    archive: Path, asset: PlannedAsset, stream: BinaryIO, reader: ArchiveReader
) -> None:
    """Pack natives/ files; e.g. ``write_packed_pak(rar, asset, out, reader)``."""

    def copier(member: str) -> MemberCopier:
        return lambda out: reader.copy_member(archive, member, out)

    write_re_pak(stream, tuple((path, copier(member)) for member, path in asset.packed))
