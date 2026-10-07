"""Remember scanned pak games so the nxm handler, a separate process, knows them."""

import json
import os
from pathlib import Path
import tempfile

from omamods.nexus_games import DOMAIN_PATTERN
from omamods.pak_games import PakOverlayGame
from omamods.re_engine_layout import PATCH_CHAINS

DETECTED_GAMES_FILE = "detected_games.json"


def _game_record(game: PakOverlayGame) -> dict[str, object]:
    return {
        "game_id": game.game_id,
        "name": game.name,
        "nexus_domain": game.nexus_domain,
        "paks_subpath": game.paks_subpath.as_posix(),
        "mods_dirname": game.mods_dirname,
        "flat_suffix_sets": [sorted(group) for group in game.flat_suffix_sets],
        "install_root": str(game.install_root),
        "signed": game.signed,
        "patch_chain": game.patch_chain,
    }


def save_detected_games(root: Path, games: tuple[PakOverlayGame, ...]) -> Path:
    """Persist a scan; for example, ``save_detected_games(storage_root, games)``."""
    path = root / DETECTED_GAMES_FILE
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=root, delete=False) as stream:
        json.dump([_game_record(game) for game in games], stream, indent=2)
    os.replace(stream.name, path)
    return path


def _text_field(record: dict[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"detected game {key}={value!r}: expected nonempty text")
    return value


def _relative_subpath(record: dict[str, object]) -> Path:
    subpath = Path(_text_field(record, "paks_subpath"))
    if subpath.is_absolute() or ".." in subpath.parts:
        raise ValueError(f"paks_subpath={str(subpath)!r}: expected a relative path")
    return subpath


def _suffix_sets(record: dict[str, object]) -> tuple[frozenset[str], ...]:
    groups = record.get("flat_suffix_sets")
    if not isinstance(groups, list) or not all(isinstance(g, list) for g in groups):
        raise ValueError(f"flat_suffix_sets={groups!r}: expected lists of suffixes")
    return tuple(frozenset(str(suffix) for suffix in group) for group in groups)


def _safe_id(record: dict[str, object], key: str) -> str:
    # IDs and domains name storage folders and URLs, so keep them plain.
    value = _text_field(record, key)
    if not DOMAIN_PATTERN.fullmatch(value.replace("-", "")):
        raise ValueError(f"detected game {key}={value!r}: expected [a-z0-9-]+")
    return value


def _domain(record: dict[str, object]) -> str:
    value = _text_field(record, "nexus_domain")
    if not DOMAIN_PATTERN.fullmatch(value):
        raise ValueError(f"detected nexus_domain={value!r}: expected [a-z0-9]+")
    return value


def _plain_name(record: dict[str, object], key: str) -> str:
    value = _text_field(record, key)
    if Path(value).name != value or value in (".", ".."):
        raise ValueError(f"detected game {key}={value!r}: expected one folder name")
    return value


def _patch_chain(record: dict[str, object]) -> str | None:
    # The chain names files written at the game root, so only known names pass.
    value = record.get("patch_chain")
    if value is None:
        return None
    if isinstance(value, str) and value in PATCH_CHAINS:
        return value
    raise ValueError(f"patch_chain={value!r}: expected null or one of {PATCH_CHAINS!r}")


def _mods_dirname(record: dict[str, object], chain: str | None) -> str:
    if chain is None:
        return _plain_name(record, "mods_dirname")
    value = record.get("mods_dirname")
    if value != "":
        raise ValueError(f"RE Engine mods_dirname={value!r}: expected ''")
    return ""


def _absolute_root(record: dict[str, object]) -> Path:
    root = Path(_text_field(record, "install_root"))
    if not root.is_absolute():
        raise ValueError(f"install_root={str(root)!r}: expected an absolute path")
    return root


def parse_detected_game(record: object) -> PakOverlayGame:
    """Validate one saved game; e.g. ``parse_detected_game({'game_id': ...})``."""
    if not isinstance(record, dict):
        raise ValueError(f"detected game={record!r}: expected an object")
    chain = _patch_chain(record)
    return PakOverlayGame(
        game_id=_safe_id(record, "game_id"),
        name=_text_field(record, "name"),
        nexus_domain=_domain(record),
        paks_subpath=_relative_subpath(record),
        mods_dirname=_mods_dirname(record, chain),
        flat_suffix_sets=_suffix_sets(record),
        install_root=_absolute_root(record),
        signed=record.get("signed") is True,
        patch_chain=chain,
    )


def load_detected_games(root: Path) -> tuple[PakOverlayGame, ...]:
    """Read the last scan, or nothing; e.g. ``load_detected_games(storage_root)``."""
    try:
        records = json.loads((root / DETECTED_GAMES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    if not isinstance(records, list):
        return ()
    games: list[PakOverlayGame] = []
    for record in records:
        try:
            games.append(parse_detected_game(record))
        except ValueError:
            continue  # A hand-edited entry must not hide the rest.
    return tuple(games)
