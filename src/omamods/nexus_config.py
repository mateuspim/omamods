"""Private TOML settings for the user's Nexus archive library."""

from dataclasses import dataclass
import json
import os
import re
from pathlib import Path
import tomllib
from typing import Mapping, Protocol

from omamods.pak_games import PAK_OVERLAY_GAMES


@dataclass(frozen=True)
class RequestedMod:
    """One explicitly selected Nexus page and optional immutable file ID."""

    game: str
    url: str
    file_id: int | None
    option: str | None


@dataclass(frozen=True)
class UserSettings:
    """Private credentials, persistent storage, and requested mods."""

    api_key: str
    storage_root: Path
    install_dirs: Mapping[str, Path]
    mods: tuple[RequestedMod, ...]


class ConfigFiles(Protocol):
    """Limit config access to two explicit operations."""

    def read_text(self, path: Path) -> str:
        """Read a config; for example, ``files.read_text(config_path)``."""
        ...

    def create_private(self, path: Path, content: str) -> None:
        """Create a private config; for example, ``files.create_private(path, text)``."""
        ...

    def replace_private(self, path: Path, content: str) -> None:
        """Rewrite a private config; for example, ``files.replace_private(path, text)``."""
        ...


class LocalConfigFiles:
    """Keep the actual user config outside the repository with mode 0600."""

    def read_text(self, path: Path) -> str:
        """Read UTF-8 TOML; for example, ``files.read_text(path)``."""
        return path.read_text(encoding="utf-8")

    def create_private(self, path: Path, content: str) -> None:
        """Create without replacing; for example, ``files.create_private(path, text)``."""
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)

    def replace_private(self, path: Path, content: str) -> None:
        """Swap in new text atomically; for example, ``files.replace_private(path, text)``."""
        partial = path.with_name(f".{path.name}.partial")
        partial.unlink(missing_ok=True)
        self.create_private(partial, content)
        os.replace(partial, path)


def default_config_path(home: Path, xdg_config_home: str | None) -> Path:
    """Use XDG config storage; e.g. ``default_config_path(Path('/home/me'), None)``."""
    root = Path(xdg_config_home) if xdg_config_home else home / ".config"
    if not root.is_absolute():
        raise ValueError(
            f"XDG_CONFIG_HOME={xdg_config_home!r}: expected an absolute path"
        )
    return root / "omamods/config.toml"


def default_storage_root(home: Path, xdg_data_home: str | None) -> Path:
    """Use persistent host storage; e.g. ``default_storage_root(home, None)``."""
    root = Path(xdg_data_home) if xdg_data_home else home / ".local/share"
    if not root.is_absolute():
        raise ValueError(f"XDG_DATA_HOME={xdg_data_home!r}: expected an absolute path")
    return root / "omamods"


def initial_config(storage_root: Path) -> str:
    """Render a private starting file; e.g. ``initial_config(Path('/data/mods'))``."""
    return (
        "# Personal Nexus API key: https://www.nexusmods.com/users/myaccount?tab=api\n"
        '[nexus]\napi_key = ""\n\n[storage]\n'
        f"root = {json.dumps(str(storage_root))}\n\n"
        '# Optional: [games.cronos]\n# install_dir = "/path/to/Cronos. The New Dawn"\n\n'
        '[[mods]]\ngame = "cronos"\n'
        'url = "https://www.nexusmods.com/cronosthenewdawn/mods/38"\n'
        "# file_id = 12345  # Set this if a page has multiple main files.\n\n"
        '# [[mods]]\n# game = "stellar-blade"\n'
        '# url = "https://www.nexusmods.com/stellarblade/mods/1"\n'
        '# option = "Folder name"  # Pick one variant folder in the archive.\n'
    )


def initialize_config(path: Path, storage_root: Path, files: ConfigFiles) -> None:
    """Create once; for example, ``initialize_config(path, storage, files)``."""
    files.create_private(path, initial_config(storage_root))


def _table(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field}={value!r}: expected a TOML table")
    return value


def _absolute_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise ValueError(f"{field}={value!r}: expected an absolute path")
    return Path(value)


def _optional_id(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise ValueError(f"file_id={value!r}: expected a positive integer")
    return value


def _optional_option(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"option={value!r}: expected a nonempty archive folder name")
    return value


def _requested_mod(value: object) -> RequestedMod:
    fields = _table(value, "mod")
    if set(fields) - {"game", "url", "file_id", "option"}:
        raise ValueError(
            f"mod fields={sorted(fields)!r}: expected game, url, file_id, option"
        )
    game, url = fields.get("game"), fields.get("url")
    if game not in PAK_OVERLAY_GAMES or not isinstance(url, str) or not url:
        raise ValueError(
            f"mod={fields!r}: expected game in {sorted(PAK_OVERLAY_GAMES)!r} and a Nexus URL"
        )
    return RequestedMod(
        str(game),
        url,
        _optional_id(fields.get("file_id")),
        _optional_option(fields.get("option")),
    )


def _install_dirs(games: dict[str, object]) -> dict[str, Path]:
    unknown = sorted(set(games) - set(PAK_OVERLAY_GAMES))
    if unknown:
        raise ValueError(
            f"games tables={unknown!r}: expected only {sorted(PAK_OVERLAY_GAMES)!r}"
        )
    tables = {key: _table(value, f"games.{key}") for key, value in games.items()}
    return {
        key: _absolute_path(table["install_dir"], f"games.{key}.install_dir")
        for key, table in tables.items()
        if "install_dir" in table
    }


def _api_key(value: object, env_key: str | None) -> str:
    if env_key is not None:
        if not env_key:
            raise ValueError("NEXUS_API_KEY='': expected a nonempty API key")
        return env_key
    if not isinstance(value, str):
        raise ValueError(f"nexus.api_key={value!r}: expected a string")
    return value


def _parsed_tables(
    source: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], object]:
    try:
        fields = _table(tomllib.loads(source), "config")
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"config TOML: expected valid TOML: {error}") from error
    games = _table(fields.get("games", {}), "games")
    return (
        _table(fields.get("nexus", {}), "nexus"),
        _table(fields.get("storage", {}), "storage"),
        games,
        fields.get("mods", []),
    )


def parse_user_config(
    source: str, fallback_root: Path, env_key: str | None
) -> UserSettings:
    """Validate private TOML; e.g. ``parse_user_config(text, root, None)``."""
    nexus, storage, games, raw_mods = _parsed_tables(source)
    if not isinstance(raw_mods, list):
        raise ValueError(f"mods={raw_mods!r}: expected an array of TOML tables")
    return UserSettings(
        api_key=_api_key(nexus.get("api_key", ""), env_key),
        storage_root=_absolute_path(
            storage.get("root", str(fallback_root)), "storage.root"
        ),
        install_dirs=_install_dirs(games),
        mods=tuple(_requested_mod(value) for value in raw_mods),
    )


def load_user_config(
    path: Path, fallback_root: Path, env_key: str | None, files: ConfigFiles
) -> UserSettings:
    """Read the private file; e.g. ``load_user_config(path, root, key, files)``."""
    try:
        return parse_user_config(files.read_text(path), fallback_root, env_key)
    except FileNotFoundError as error:
        raise ValueError(
            f"config={str(path)!r}: expected a file; run 'omamods config init'"
        ) from error


def with_api_key(source: str, api_key: str) -> str:
    """Set nexus.api_key in TOML text; e.g. ``with_api_key(text, 'abc')``."""
    if not api_key or any(c.isspace() or c in '"\\' for c in api_key):
        raise ValueError("Nexus API key: expected one token without spaces or quotes")
    line = f"api_key = {json.dumps(api_key)}"
    if re.search(r"(?m)^api_key\s*=.*$", source):
        return re.sub(r"(?m)^api_key\s*=.*$", lambda _: line, source, count=1)
    if re.search(r"(?m)^\[nexus\]\s*$", source):
        return re.sub(
            r"(?m)^\[nexus\]\s*$", lambda _: f"[nexus]\n{line}", source, count=1
        )
    return f"[nexus]\n{line}\n\n{source}"


def save_api_key(
    path: Path, storage_root: Path, api_key: str, files: ConfigFiles
) -> None:
    """Store the key privately; e.g. ``save_api_key(path, root, key, files)``."""
    try:
        source = files.read_text(path)
    except FileNotFoundError:
        initialize_config(path, storage_root, files)
        source = files.read_text(path)
    updated = with_api_key(source, api_key)
    parse_user_config(updated, storage_root, None)
    files.replace_private(path, updated)
