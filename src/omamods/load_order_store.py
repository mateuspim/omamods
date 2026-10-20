"""Remember which containers the user renamed to load last, across reinstalls.

Each choice lives beside the file's ownership record as ``<record>.load-order``
and maps the archive's container stem to the chosen one, both relative to
Paks (``{"~mods/Fix_P": "~mods/Fix_1_P"}``). Reverting deletes the record but
keeps this file, so reinstalling or updating the same file reuses the name.
"""

from dataclasses import replace
import json
import os
from pathlib import Path, PurePosixPath
import tempfile

from omamods.pak_archive import ASSET_SUFFIXES, PlannedAsset

LOAD_ORDER_SUFFIX = ".load-order"


def load_order_path(record: Path) -> Path:
    """Name a record's choices file; e.g. ``load_order_path(state / '7.json')``.

    The suffix is not ``.json``, so listing a mod's records never picks it up.
    """
    return record.with_suffix(LOAD_ORDER_SUFFIX)


def _valid_stem(stem: object) -> bool:
    if not isinstance(stem, str) or "\\" in stem:
        return False
    pure = PurePosixPath(stem)
    return not pure.is_absolute() and ".." not in pure.parts and len(pure.parts) > 1


def read_load_order(path: Path) -> dict[str, str]:
    """Read saved choices, or none; e.g. ``read_load_order(load_order_path(r))``."""
    if not path.is_file():
        return {}
    try:
        choices = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError(f"load order={str(path)!r}: expected JSON") from error
    if not isinstance(choices, dict) or not all(
        _valid_stem(key) and _valid_stem(value) for key, value in choices.items()
    ):
        raise ValueError(
            f"load order={str(path)!r} value={choices!r}: expected "
            '{"~mods/Name_P": "~mods/Name_1_P"}'
        )
    return dict(choices)


def write_load_order(path: Path, choices: dict[str, str]) -> None:
    """Save choices atomically, removing the file when empty.

    Example: ``write_load_order(path, {'~mods/Fix_P': '~mods/Fix_1_P'})``.
    """
    if not choices:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=".", delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(choices, stream, indent=2, sort_keys=True)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def remember_choice(choices: dict[str, str], old: str, new: str) -> dict[str, str]:
    """Record a rename from ``old`` to ``new``, keyed by the archive's stem.

    Example: ``remember_choice({}, '~mods/Fix_P', '~mods/Fix_1_P')``.
    """
    original = next((key for key, value in choices.items() if value == old), old)
    updated = {key: value for key, value in choices.items() if key != original}
    if new != original:
        updated[original] = new
    return updated


def _renamed(asset: PlannedAsset, choices: dict[str, str]) -> PlannedAsset:
    target = PurePosixPath(asset.target.as_posix())
    if asset.beside_exe or asset.user_config:
        return asset
    if target.suffix.lower() not in ASSET_SUFFIXES:
        return asset
    chosen = choices.get(target.with_suffix("").as_posix())
    if chosen is None:
        return asset
    return replace(asset, target=Path(chosen + target.suffix))


def apply_load_order(
    planned: tuple[PlannedAsset, ...], choices: dict[str, str]
) -> tuple[PlannedAsset, ...]:
    """Rename planned containers the user chose to load last.

    Example: ``apply_load_order(plan, {'~mods/Fix_P': '~mods/Fix_1_P'})``.
    """
    return tuple(_renamed(asset, choices) for asset in planned)
