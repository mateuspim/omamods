"""Validate the discovery manifest before using its fields as paths or IDs."""

from dataclasses import dataclass
from pathlib import Path
import re

from omamods.filesystem import ReadableFiles
from omamods.yaml_codec import ManifestDecoder

ADAPTER_KINDS: tuple[str, ...] = (
    "undecided",
    "direct-overlay",
    "external-manager",
    "archive-patcher",
    "game-native",
)


@dataclass(frozen=True)
class GameManifest:
    """A validated game adapter declaration."""

    id: str
    name: str
    status: str
    platforms: tuple[str, ...]
    adapter: str
    notes: tuple[str, ...]
    steam_app_id: int | None


def _text_field(fields: dict[str, object], key: str) -> str:
    value = fields.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}={value!r}: expected a nonempty string")
    return value


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field}={value!r}: expected a list of nonempty strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field}={value!r}: expected a list of nonempty strings")
    return tuple(value)


def _manifest_fields(value: object) -> dict[str, object]:
    allowed = {"id", "name", "status", "platforms", "adapter", "notes", "steam_app_id"}
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"manifest={value!r}: expected a mapping with string keys")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(
            f"fields={sorted(unknown)!r}: expected only {sorted(allowed)!r}"
        )
    return value


def _choice(fields: dict[str, object], key: str, choices: tuple[str, ...]) -> str:
    value = _text_field(fields, key)
    if value not in choices:
        raise ValueError(f"{key}={value!r}: expected one of {choices!r}")
    return value


def _steam_id(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise ValueError(f"steam_app_id={value!r}: expected a positive integer or null")
    return value


def _game_slug(fields: dict[str, object]) -> str:
    game_id = _text_field(fields, "id")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", game_id):
        raise ValueError(
            f"id={game_id!r}: expected a lowercase slug, e.g. 'dawnwalker'"
        )
    return game_id


def _platforms(fields: dict[str, object]) -> tuple[str, ...]:
    platforms = _string_list(fields.get("platforms"), "platforms")
    if platforms != ("steam",):
        raise ValueError(f"platforms={platforms!r}: expected ['steam'] for discovery")
    return platforms


def validate_manifest(value: object) -> GameManifest:
    """Validate decoded fields; for example, ``validate_manifest(decoder.decode(text))``."""
    fields = _manifest_fields(value)
    return GameManifest(
        id=_game_slug(fields),
        name=_text_field(fields, "name"),
        status=_choice(fields, "status", ("discovery", "ready")),
        platforms=_platforms(fields),
        adapter=_choice(fields, "adapter", ADAPTER_KINDS),
        notes=_string_list(fields.get("notes", []), "notes"),
        steam_app_id=_steam_id(fields.get("steam_app_id")),
    )


def load_catalog(
    root: Path, files: ReadableFiles, decoder: ManifestDecoder
) -> tuple[GameManifest, ...]:
    """Load the Git catalog; for example, ``load_catalog(Path('games'), files, decoder)``."""
    if not files.is_dir(root):
        raise ValueError(
            f"games directory {str(root)!r}: expected an existing directory"
        )
    paths = files.glob(root, "*/game.yml")
    if not paths:
        raise ValueError(
            f"games directory {str(root)!r}: expected at least one */game.yml"
        )
    return tuple(_load_game(path, files, decoder) for path in paths)


def _load_game(
    path: Path, files: ReadableFiles, decoder: ManifestDecoder
) -> GameManifest:
    try:
        manifest = validate_manifest(decoder.decode(files.read_text(path)))
        if manifest.id != path.parent.name:
            raise ValueError(
                f"id={manifest.id!r}: expected directory name {path.parent.name!r}"
            )
        return manifest
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error
