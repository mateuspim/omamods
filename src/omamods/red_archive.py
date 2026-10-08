"""Map a Cyberpunk 2077 mod archive onto the game folder.

Cyberpunk mods and their frameworks (RED4ext, ArchiveXL, TweakXL, Codeware,
redscript, Cyber Engine Tweaks) all ask to be extracted into the game folder,
so members under a game-root folder (archive/, bin/, engine/, r6/, red4ext/)
keep their path. Loose .archive and .xl files go to archive/pc/mod. REDmod
packages (mods/) need REDmod's deploy step and FOMOD installers need choices,
so both are refused.
"""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from omamods.pak_archive import PlannedAsset, archive_member_path
from omamods.pak_games import PakOverlayGame

RED_GAME_FOLDERS = frozenset({"archive", "bin", "engine", "r6", "red4ext"})
# Top-level folders the game ships; a revert never removes them, even empty.
RED_SHIPPED_FOLDERS = frozenset({"archive", "bin", "engine", "r6"})
RED_LOOSE_SUFFIXES = frozenset({".archive", ".xl"})
# Loose code without a game-root folder has no safe destination to guess.
RED_UNPLACEABLE_SUFFIXES = frozenset(
    {".reds", ".lua", ".dll", ".asi", ".exe", ".yaml", ".yml", ".tweak"}
)
RED_REFUSED_FOLDERS = {
    "mods": "REDmod packages need REDmod's deploy step",
    "fomod": "FOMOD installers need choices OmaMods cannot make",
}


@dataclass(frozen=True)
class RedModFile:
    """One archive member, its variant folder, and its game-relative path."""

    member: str
    root: str
    target: PurePosixPath


def _refuse_folders(member: str, path: PurePosixPath, anchor: int | None) -> None:
    # Only folders above the game-root folder count: CET keeps its own mods/
    # deep in bin/x64/plugins/cyber_engine_tweaks/ (Native Settings UI, 3518).
    above = path.parts[:-1] if anchor is None else path.parts[:anchor]
    for part in above:
        reason = RED_REFUSED_FOLDERS.get(part.lower())
        if reason is not None:
            raise ValueError(
                f"archive member={member!r}: expected game-folder files; {reason}"
            )


def _anchor_index(path: PurePosixPath) -> int | None:
    folders = [part.lower() for part in path.parts[:-1]]
    return next((i for i, p in enumerate(folders) if p in RED_GAME_FOLDERS), None)


def _anchored(member: str, path: PurePosixPath, index: int) -> RedModFile:
    # The game's own folders are lowercase; on a case-sensitive disk "Bin/"
    # would become a second folder beside "bin/".
    parts = (path.parts[index].lower(), *path.parts[index + 1 :])
    root = PurePosixPath(*path.parts[:index]).as_posix()
    return RedModFile(member, root, PurePosixPath(*parts))


def _loose(member: str, path: PurePosixPath, mods_dirname: str) -> RedModFile | None:
    suffix = path.suffix.lower()
    if suffix in RED_UNPLACEABLE_SUFFIXES:
        raise ValueError(
            f"archive member={member!r}: expected it under a game folder "
            f"({', '.join(sorted(RED_GAME_FOLDERS))}); its destination is unknown"
        )
    if suffix not in RED_LOOSE_SUFFIXES:
        return None  # Readmes, pictures, and other notes stay in staging.
    target = PurePosixPath(mods_dirname, path.name)
    return RedModFile(member, path.parent.as_posix(), target)


def _mod_file(member: str, mods_dirname: str) -> RedModFile | None:
    path = archive_member_path(member)
    index = _anchor_index(path)
    _refuse_folders(member, path, index)
    if index is not None:
        return _anchored(member, path, index)
    return _loose(member, path, mods_dirname)


def red_mod_files(
    members: tuple[str, ...], game: PakOverlayGame
) -> tuple[RedModFile, ...]:
    """Place usable members; e.g. ``red_mod_files(('bin/x64/a.dll',), cyberpunk)``."""
    found = (
        _mod_file(member, game.mods_dirname)
        for member in members
        if not member.endswith("/")
    )
    usable = (file for file in found if file is not None)
    return tuple(sorted(usable, key=lambda file: file.target.as_posix()))


def _variant_roots(files: tuple[RedModFile, ...]) -> list[str]:
    return sorted({file.root for file in files})


def _in_root(root: str, option: str) -> bool:
    return root == option or option in PurePosixPath(root).parts


def _chosen(
    files: tuple[RedModFile, ...], option: str | None, game: PakOverlayGame
) -> tuple[RedModFile, ...]:
    roots = _variant_roots(files)
    if option is None and len(roots) > 1:
        raise ValueError(
            f"{game.name} archive folders={roots!r}: expected one variant; pick one"
        )
    chosen = tuple(f for f in files if option is None or _in_root(f.root, option))
    if not chosen:
        raise ValueError(f"option={option!r}: expected a folder from {roots!r}")
    return chosen


def _require_unique_targets(files: tuple[RedModFile, ...]) -> None:
    # Wine opens game files case-insensitively, so A.archive and a.archive clash.
    targets = [file.target.as_posix().lower() for file in files]
    duplicates = sorted({target for target in targets if targets.count(target) > 1})
    if duplicates:
        raise ValueError(
            f"game paths={duplicates!r}: expected each once in the chosen variant, "
            "ignoring case"
        )


def plan_red_archives(
    members: tuple[str, ...], game: PakOverlayGame, option: str | None
) -> tuple[PlannedAsset, ...]:
    """Place files in the game folder; e.g. ``plan_red_archives(names, cyberpunk, None)``."""
    files = red_mod_files(members, game)
    if not files:
        raise ValueError(
            f"{game.name} archive members={list(members)!r}: expected .archive "
            f"files or game folders ({', '.join(sorted(RED_GAME_FOLDERS))})"
        )
    chosen = _chosen(files, option, game)
    _require_unique_targets(chosen)
    return tuple(
        PlannedAsset(f.member, Path(f.target), allow_empty=True) for f in chosen
    )


def red_archive_variants(
    members: tuple[str, ...], game: PakOverlayGame
) -> tuple[str, ...]:
    """List choosable variants (empty if none); e.g. ``red_archive_variants(names, cp)``."""
    roots = _variant_roots(red_mod_files(members, game))
    return tuple(roots) if len(roots) > 1 else ()


def is_removable_red_folder(game_root: Path, folder: Path) -> bool:
    """Allow pruning an emptied folder; e.g. ``is_removable_red_folder(root, f)``."""
    if folder == game_root or not folder.is_relative_to(game_root):
        return False
    shipped = folder.parent == game_root and folder.name in RED_SHIPPED_FOLDERS
    return not shipped and folder.is_dir() and not any(folder.iterdir())


def is_red_game_path(relative: str) -> bool:
    """Accept owned paths on revert; e.g. ``is_red_game_path('bin/x64/winmm.dll')``."""
    path = PurePosixPath(relative)
    return (
        not path.is_absolute()
        and len(path.parts) >= 2
        and path.parts[0] in RED_GAME_FOLDERS
        and not {"..", "."} & set(path.parts)
    )
