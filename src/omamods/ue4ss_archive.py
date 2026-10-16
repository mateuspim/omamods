"""Map a mod archive that bundles UE4SS onto an Unreal game's Binaries/Win64.

Authors such as MGS Delta's BetterUncapFPS (Nexus metalgearsoliddeltasnakeeater
mod 47) ship UE4SS itself with their Lua mod enabled in its mods.txt: a proxy
DLL (dwmapi.dll) plus a ue4ss/ folder, both extracted beside the game's
shipping executable, and sometimes an Engine.ini for the Proton prefix. Standalone UE4SS mods would have to be merged into an
existing mods.txt, so only full bundles are accepted for now.
"""

from pathlib import Path, PurePosixPath

from omamods.red_frameworks import PathProbe
from omamods.pak_archive import PlannedAsset, archive_member_path
from omamods.pak_games import PakOverlayGame
from omamods.ue_config import canonical_config_name, is_ue_config_name

UE4SS_FOLDER = "ue4ss"
UE4SS_CORE = "ue4ss/UE4SS.dll"
# UE4SS 3 loads through dwmapi.dll; 2.x releases used xinput1_3.dll.
UE4SS_PROXY_DLLS = frozenset({"dwmapi.dll", "xinput1_3.dll"})
# Relative to <Project>/Content/Paks, where the Unreal installer starts.
BINARIES_FROM_PAKS = PurePosixPath("../../Binaries/Win64")
BINARIES_LABEL = "Binaries/Win64"
# Lua mods rewrite their own settings (BetterUncapFPS' UncapFPS_config.txt),
# so these may differ from the archive when the mod is uninstalled.
EDITABLE_SUFFIXES = frozenset({".txt", ".ini", ".json", ".cfg"})
# Readmes and pictures beside the bundle stay in staging.
NOTE_SUFFIXES = frozenset({".txt", ".md", ".ini", ".png", ".jpg", ".jpeg", ".url"})


def is_ue4ss_archive(members: tuple[str, ...]) -> bool:
    """Spot a bundle; e.g. ``is_ue4ss_archive(('ue4ss/UE4SS.dll',)) is True``."""
    return any(_ue4ss_index(PurePosixPath(member)) is not None for member in members)


def _ue4ss_index(path: PurePosixPath) -> int | None:
    folders = [part.lower() for part in path.parts[:-1]]
    return folders.index(UE4SS_FOLDER) if UE4SS_FOLDER in folders else None


def _bundle_base(members: tuple[str, ...]) -> PurePosixPath:
    bases = set()
    for member in members:
        path = PurePosixPath(member)
        index = _ue4ss_index(path)
        if index is not None:
            bases.add(PurePosixPath(*path.parts[:index]))
    if len(bases) != 1:
        found = sorted(base.as_posix() for base in bases)
        raise ValueError(
            f"UE4SS folders under={found!r}: expected exactly one ue4ss/ folder"
        )
    return bases.pop()


def _planned_member(
    member: str, base: PurePosixPath, game: PakOverlayGame
) -> PlannedAsset | None:
    path = archive_member_path(member)
    if base not in path.parents:
        return _outside_bundle(member, path)
    relative = path.relative_to(base)
    if len(relative.parts) == 1 and is_ue_config_name(relative.name):
        return _config_member(member, relative.name, game)
    if relative.parts[0].lower() == UE4SS_FOLDER:
        target = Path(UE4SS_FOLDER, *relative.parts[1:])
        editable = target.suffix.lower() in EDITABLE_SUFFIXES
        return PlannedAsset(
            member, target, allow_empty=True, user_editable=editable, beside_exe=True
        )
    if len(relative.parts) == 1 and relative.name.lower() in UE4SS_PROXY_DLLS:
        return PlannedAsset(member, Path(relative.name.lower()), beside_exe=True)
    return _outside_bundle(member, path)


def _config_member(member: str, name: str, game: PakOverlayGame) -> PlannedAsset | None:
    # Without a Steam app the Proton prefix is unknown; the file stays in staging.
    if game.steam_app_id is None:
        return None
    target = Path(canonical_config_name(name))
    return PlannedAsset(member, target, user_editable=True, user_config=True)


def _outside_bundle(member: str, path: PurePosixPath) -> None:
    if path.suffix.lower() in NOTE_SUFFIXES:
        return None
    raise ValueError(
        f"archive member={member!r}: expected only a proxy DLL "
        f"({', '.join(sorted(UE4SS_PROXY_DLLS))}), the ue4ss/ folder, and notes "
        "beside it; its destination is unknown"
    )


def _require_full_bundle(
    planned: tuple[PlannedAsset, ...], game: PakOverlayGame
) -> None:
    targets = {asset.target.as_posix().lower() for asset in planned}
    if UE4SS_CORE.lower() in targets and targets & UE4SS_PROXY_DLLS:
        return
    raise ValueError(
        f"{game.name} archive: expected UE4SS itself ({UE4SS_CORE} and "
        f"{' or '.join(sorted(UE4SS_PROXY_DLLS))}); standalone UE4SS mods are "
        "not supported yet"
    )


def plan_ue4ss_bundle(
    members: tuple[str, ...], game: PakOverlayGame
) -> tuple[PlannedAsset, ...]:
    """Place a UE4SS bundle beside the exe; e.g. ``plan_ue4ss_bundle(names, mgs)``."""
    files = tuple(member for member in members if not member.endswith("/"))
    base = _bundle_base(files)
    found = (_planned_member(member, base, game) for member in files)
    planned = tuple(asset for asset in found if asset is not None)
    _require_full_bundle(planned, game)
    _require_unique_targets(planned)
    return planned


def _require_unique_targets(planned: tuple[PlannedAsset, ...]) -> None:
    # Wine opens files case-insensitively, so Mods/ and mods/ would clash.
    targets = [asset.target.as_posix().lower() for asset in planned]
    duplicates = sorted({target for target in targets if targets.count(target) > 1})
    if duplicates:
        raise ValueError(
            f"UE4SS paths={duplicates!r}: expected each once, ignoring case"
        )


def ue4ss_binaries(paks: Path) -> Path:
    """Find the exe folder; e.g. ``ue4ss_binaries(Path('/g/MGSDelta/Content/Paks'))``."""
    binaries = (paks / BINARIES_FROM_PAKS).resolve()
    if not binaries.is_dir():
        raise ValueError(
            f"Binaries={str(binaries)!r}: expected the folder holding the game's "
            "shipping executable"
        )
    return binaries


def is_ue4ss_game_path(relative: str) -> bool:
    """Accept owned paths on revert; e.g. ``is_ue4ss_game_path('ue4ss/UE4SS.dll')``."""
    path = PurePosixPath(relative)
    if path.is_absolute() or {"..", "."} & set(path.parts):
        return False
    if len(path.parts) == 1:
        return path.name in UE4SS_PROXY_DLLS
    return path.parts[0] == UE4SS_FOLDER


def ue4ss_proxies_on_disk(binaries: Path, exists: PathProbe) -> frozenset[str]:
    """DLLs UE4SS loads through; e.g. ``ue4ss_proxies_on_disk(win64, Path.exists)``."""
    if not exists(binaries / UE4SS_CORE):
        return frozenset()
    return frozenset(
        Path(dll).stem for dll in UE4SS_PROXY_DLLS if exists(binaries / dll)
    )
