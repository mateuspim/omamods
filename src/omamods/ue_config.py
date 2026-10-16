"""Place an Unreal mod's Engine.ini in the game's config folder in the Proton prefix.

BetterUncapFPS (MGS Delta mod 47) ships an Engine.ini beside its UE4SS bundle
that belongs in AppData/Local/MGSDelta/Saved/Config/Windows, where the game
already keeps its own. The install sets the game's file aside and the
uninstall puts it back.
"""

from pathlib import Path, PurePosixPath

from omamods.pak_games import PakOverlayGame
from omamods.proton_runtime import steam_prefix

# The override files Unreal reads from Saved/Config/<platform>/.
UE_CONFIG_NAMES = frozenset(
    {"engine.ini", "game.ini", "input.ini", "scalability.ini", "gameusersettings.ini"}
)
# Unreal 5 games use Windows/; Unreal 4 shipping builds use WindowsNoEditor/.
PLATFORM_FOLDERS = ("Windows", "WindowsNoEditor")
LOCAL_APPDATA = PurePosixPath("drive_c/users/steamuser/AppData/Local")
CONFIG_LABEL = "Proton prefix Saved/Config"
CONFIG_RECORD_SUFFIX = ".config"


def is_ue_config_name(name: str) -> bool:
    """Spot an override file; e.g. ``is_ue_config_name('Engine.ini') is True``."""
    return name.lower() in UE_CONFIG_NAMES


def is_ue_config_path(relative: str) -> bool:
    """Accept owned config paths on revert; e.g. ``is_ue_config_path('Engine.ini')``."""
    path = PurePosixPath(relative)
    return len(path.parts) == 1 and path.name in _canonical_names()


def _canonical_names() -> frozenset[str]:
    return frozenset(canonical_config_name(name) for name in UE_CONFIG_NAMES)


def canonical_config_name(name: str) -> str:
    """Unreal's own spelling; e.g. ``canonical_config_name('ENGINE.INI') == 'Engine.ini'``."""
    stem = name[: -len(".ini")].lower()
    spelled = "GameUserSettings" if stem == "gameusersettings" else stem.capitalize()
    return f"{spelled}.ini"


def ue_config_folder(paks: Path, game: PakOverlayGame) -> Path:
    """Find Saved/Config/<platform>; e.g. ``ue_config_folder(paks, mgs_delta)``."""
    if game.steam_app_id is None:
        raise ValueError(f"{game.name} steam_app_id=None: expected a Steam game")
    game_root = _game_root(paks, game)
    project = game.paks_subpath.parts[0]
    saved = steam_prefix(game_root, game.steam_app_id) / LOCAL_APPDATA / project
    config = saved / "Saved/Config"
    for platform in PLATFORM_FOLDERS:
        if (config / platform).is_dir():
            return config / platform
    raise ValueError(
        f"config folder={str(config / PLATFORM_FOLDERS[0])!r}: expected it to "
        f"exist; launch {game.name} once so it creates its settings, then install"
    )


def _game_root(paks: Path, game: PakOverlayGame) -> Path:
    root = paks
    for _ in game.paks_subpath.parts:
        root = root.parent
    return root


def config_record(record: Path) -> Path:
    """Name the prefix half of an install; e.g. ``config_record(state / '321.json')``.

    The file ID stays first, so the record still counts as that file's install.
    """
    return record.with_name(f"{record.stem}{CONFIG_RECORD_SUFFIX}{record.suffix}")
