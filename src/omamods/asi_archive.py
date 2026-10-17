"""Map an ASI plugin archive onto the folder holding a game's executable.

Fixes such as Lyall's MGSVFix (codeberg.org/Lyall/MGSVFix) ship Ultimate ASI
Loader as a proxy DLL (winmm.dll) beside the plugin (MGSVFix.asi) and its
settings (MGSVFix.ini), all extracted next to the game's executable. The
loader also reads plugins from scripts/ and plugins/ below that folder.
"""

from pathlib import Path, PurePosixPath

from omamods.pak_archive import PlannedAsset, archive_member_path
from omamods.pak_games import PakOverlayGame
from omamods.red_frameworks import PathProbe

ASI_SUFFIX = ".asi"
# Names Ultimate ASI Loader is shipped under; Proton prefers its own builtin
# copy of each unless the launch options override it.
ASI_LOADER_DLLS = frozenset({"dinput8.dll", "dsound.dll", "version.dll", "winmm.dll"})
# How launch-option hints name it; winmm.dll alone would read as RED4ext.
ASI_LOADER_LABEL = "ASI loader"
ASI_PLUGIN_FOLDERS = frozenset({"scripts", "plugins"})
PLUGIN_SUFFIXES = frozenset({ASI_SUFFIX, ".ini"})
# Readmes stay in staging; Lyall's archives also carry an empty marker file
# named EXTRACT_TO_GAME_FOLDER, which has no suffix.
NOTE_SUFFIXES = frozenset({"", ".txt", ".md", ".url", ".png", ".jpg", ".jpeg"})
SNAKEBITE_SUFFIX = ".mgsv"


def is_asi_archive(members: tuple[str, ...]) -> bool:
    """Spot ASI plugins; e.g. ``is_asi_archive(('MGSVFix.asi',)) is True``."""
    return any(PurePosixPath(m).suffix.lower() == ASI_SUFFIX for m in members)


def _plugin_base(files: tuple[str, ...], game: PakOverlayGame) -> PurePosixPath:
    # The shallowest .asi decides the folder that maps onto the game's, so a
    # zip wrapping everything in MGSVFix_0.0.3/ installs the same way.
    plugins = [archive_member_path(m) for m in files if _is_plugin(m)]
    if not plugins:
        raise ValueError(_no_plugin_message(files, game))
    shallowest = min(plugins, key=lambda path: len(path.parts))
    base = shallowest.parent
    if base.name.lower() in ASI_PLUGIN_FOLDERS:
        return base.parent
    return base


def _is_plugin(member: str) -> bool:
    return PurePosixPath(member).suffix.lower() == ASI_SUFFIX


def _no_plugin_message(files: tuple[str, ...], game: PakOverlayGame) -> str:
    if any(PurePosixPath(m).suffix.lower() == SNAKEBITE_SUFFIX for m in files):
        return (
            f"{game.name} archive members={list(files)!r}: expected .asi plugins; "
            "SnakeBite .mgsv packages need SnakeBite, which OmaMods does not run yet"
        )
    return f"{game.name} archive members={list(files)!r}: expected .asi plugins"


def _planned_member(member: str, base: PurePosixPath) -> PlannedAsset | None:
    path = archive_member_path(member)
    relative = path.relative_to(base) if base in path.parents else None
    if relative is None:
        return _note_only(member, path)
    if len(relative.parts) == 1 and relative.name.lower() in ASI_LOADER_DLLS:
        return PlannedAsset(member, Path(relative.name.lower()))
    if is_asi_game_path(relative.as_posix()):
        editable = relative.suffix.lower() != ASI_SUFFIX
        return PlannedAsset(member, Path(relative), user_editable=editable)
    return _note_only(member, path)


def _note_only(member: str, path: PurePosixPath) -> None:
    if path.suffix.lower() in NOTE_SUFFIXES:
        return None
    raise ValueError(
        f"archive member={member!r}: expected only .asi plugins, their .ini "
        f"files, a loader DLL ({', '.join(sorted(ASI_LOADER_DLLS))}), and "
        "notes; its destination is unknown"
    )


def _require_unique_targets(planned: tuple[PlannedAsset, ...]) -> None:
    # Wine opens files case-insensitively, so Scripts/ and scripts/ would clash.
    targets = [asset.target.as_posix().lower() for asset in planned]
    duplicates = sorted({target for target in targets if targets.count(target) > 1})
    if duplicates:
        raise ValueError(f"ASI paths={duplicates!r}: expected each once, ignoring case")


def plan_asi_bundle(
    members: tuple[str, ...], game: PakOverlayGame
) -> tuple[PlannedAsset, ...]:
    """Place plugins beside the exe; e.g. ``plan_asi_bundle(('MGSVFix.asi',), mgsv)``.

    The loader DLL is optional, since another mod may already provide it.
    """
    files = tuple(member for member in members if not member.endswith("/"))
    base = _plugin_base(files, game)
    found = (_planned_member(member, base) for member in files)
    planned = tuple(asset for asset in found if asset is not None)
    _require_unique_targets(planned)
    return planned


def is_asi_game_path(relative: str) -> bool:
    """Accept owned paths on revert; e.g. ``is_asi_game_path('MGSVFix.asi')``."""
    path = PurePosixPath(relative)
    if path.is_absolute() or {"..", "."} & set(path.parts) or not path.parts:
        return False
    if len(path.parts) == 1 and path.name.lower() in ASI_LOADER_DLLS:
        return True
    if path.suffix.lower() not in PLUGIN_SUFFIXES:
        return False
    if len(path.parts) == 1:
        return True
    return path.parts[0].lower() in ASI_PLUGIN_FOLDERS


def is_removable_asi_folder(root: Path, folder: Path) -> bool:
    """Prune emptied plugin folders; e.g. ``is_removable_asi_folder(game, game / 'scripts')``."""
    if folder == root or not folder.is_relative_to(root):
        return False
    top = folder.relative_to(root).parts[0].lower()
    if top not in ASI_PLUGIN_FOLDERS:
        return False
    return folder.is_dir() and not any(folder.iterdir())


def asi_loaders_on_disk(root: Path, exists: PathProbe) -> frozenset[str]:
    """DLLs an ASI loader uses; e.g. ``asi_loaders_on_disk(game, Path.exists)``."""
    return frozenset(Path(dll).stem for dll in ASI_LOADER_DLLS if exists(root / dll))
