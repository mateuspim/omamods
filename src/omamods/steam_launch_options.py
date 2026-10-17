"""Read a game's Steam launch options from every local Steam user's config."""

from pathlib import Path

from omamods.filesystem import ReadableFiles
from omamods.keyvalues import KeyValues, parse_keyvalues

LOCALCONFIG_PATTERN = "userdata/*/config/localconfig.vdf"
APPS_PATH = ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps")


def _child(block: KeyValues, key: str) -> KeyValues | None:
    # Steam writes "apps" and "Apps" depending on its version.
    for name, value in block.items():
        if name.lower() == key.lower() and isinstance(value, dict):
            return value
    return None


def app_launch_options(document: KeyValues, app_id: str) -> str | None:
    """Read one app's options; e.g. ``app_launch_options(parsed, '287700')``."""
    block: KeyValues | None = document
    for key in (*APPS_PATH, app_id):
        block = _child(block, key) if block is not None else None
    value = block.get("LaunchOptions") if block is not None else None
    return value if isinstance(value, str) else None


def steam_launch_options(
    steam_roots: tuple[Path, ...], app_id: str, files: ReadableFiles
) -> tuple[str, ...]:
    """List each user's options; e.g. ``steam_launch_options(roots, '1091500', files)``."""
    found: list[str] = []
    for root in steam_roots:
        for config in files.glob(root, LOCALCONFIG_PATTERN):
            try:
                options = app_launch_options(
                    parse_keyvalues(files.read_text(config)), app_id
                )
            except (OSError, ValueError):
                continue  # Another user's unreadable config is not this game's.
            if options is not None:
                found.append(options)
    return tuple(found)
