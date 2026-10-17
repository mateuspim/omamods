"""Write a game's Steam launch options into each Steam user's localconfig.vdf.

Only the one value changes: the file is edited as text at the token's
position, so Steam's own layout and every other setting stay byte for byte.
Steam keeps this file in memory and writes it back when it exits, so callers
must close Steam first (see ``steam_process``) or the edit is lost.
"""

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import tempfile

from omamods.keyvalues import parse_keyvalues
from omamods.steam_launch_options import (
    APPS_PATH,
    LOCALCONFIG_PATTERN,
    app_launch_options,
)

TOKEN_PATTERN = re.compile(r'\s+|//[^\n]*|"(?:\\.|[^"\\])*"|[{}]|[^\s{}"]+')
LAUNCH_KEY = "LaunchOptions"


@dataclass(frozen=True)
class _Token:
    text: str
    start: int
    end: int

    @property
    def key(self) -> str:
        quoted = self.text.startswith('"')
        return (self.text[1:-1] if quoted else self.text).lower()


def _tokens(source: str) -> tuple[_Token, ...]:
    found: list[_Token] = []
    position = 0
    while position < len(source):
        match = TOKEN_PATTERN.match(source, position)
        if match is None:
            raise ValueError(
                f"localconfig {source[position:position + 40]!r}: expected VDF text"
            )
        text, position = match.group(), match.end()
        if not text.isspace() and not text.startswith("//"):
            found.append(_Token(text, match.start(), match.end()))
    return tuple(found)


def _block_end(tokens: tuple[_Token, ...], opening: int) -> int:
    depth = 0
    for index in range(opening, len(tokens)):
        depth += {"{": 1, "}": -1}.get(tokens[index].text, 0)
        if depth == 0:
            return index
    raise ValueError(f"localconfig block at {tokens[opening].start}: expected '}}'")


def _pairs(tokens: tuple[_Token, ...], start: int, stop: int) -> list[tuple[int, int]]:
    # (key index, value index) at one nesting level; a block value is its '{'.
    pairs: list[tuple[int, int]] = []
    index = start
    while index + 1 < stop:
        pairs.append((index, index + 1))
        value = tokens[index + 1]
        index = _block_end(tokens, index + 1) + 1 if value.text == "{" else index + 2
    return pairs


def _app_block(tokens: tuple[_Token, ...], app_id: str) -> tuple[int, int]:
    start, stop = 0, len(tokens)
    for name in (*APPS_PATH, app_id):
        found = next(
            (
                value
                for key, value in _pairs(tokens, start, stop)
                if tokens[key].key == name.lower() and tokens[value].text == "{"
            ),
            None,
        )
        if found is None:
            raise ValueError(
                f"localconfig block {name!r}: expected app {app_id} to be listed; "
                "open the game's Properties in Steam once"
            )
        start, stop = found + 1, _block_end(tokens, found)
    return start, stop


def _quoted(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _indent_after(source: str, token: _Token) -> str:
    # Steam indents with tabs; a child sits one tab deeper than its parent key.
    line_start = source.rfind("\n", 0, token.start) + 1
    leading = source[line_start : token.start]
    return leading[: len(leading) - len(leading.lstrip("\t"))] + "\t"


def set_launch_options(source: str, app_id: str, line: str) -> str:
    """Set one app's options in VDF text; e.g. ``set_launch_options(text, '287700', '%command%')``."""
    tokens = _tokens(source.lstrip("\ufeff"))
    offset = len(source) - len(source.lstrip("\ufeff"))
    start, stop = _app_block(tokens, app_id)
    existing = next(
        (
            value
            for key, value in _pairs(tokens, start, stop)
            if tokens[key].key == LAUNCH_KEY.lower() and tokens[value].text != "{"
        ),
        None,
    )
    if existing is not None:
        token = tokens[existing]
        edited = _replaced(source, offset, token.start, token.end, _quoted(line))
    else:
        opening = tokens[start - 1]
        indent = _indent_after(source, tokens[start - 2])
        entry = f'\n{indent}"{LAUNCH_KEY}"\t\t{_quoted(line)}'
        edited = _replaced(source, offset, opening.end, opening.end, entry)
    _require_written(edited, app_id, line)
    return edited


def _replaced(source: str, offset: int, start: int, end: int, text: str) -> str:
    return source[: offset + start] + text + source[offset + end :]


def _require_written(edited: str, app_id: str, line: str) -> None:
    found = app_launch_options(parse_keyvalues(edited), app_id)
    if found != line:
        raise ValueError(
            f"localconfig app {app_id} LaunchOptions={found!r}: expected {line!r}"
        )


def localconfig_paths(steam_roots: tuple[Path, ...]) -> tuple[Path, ...]:
    """Find each user's config once; e.g. ``localconfig_paths((Path('~/.steam/steam'),))``."""
    # ~/.steam/steam is usually a link to ~/.local/share/Steam.
    unique: dict[Path, Path] = {}
    for root in steam_roots:
        for config in sorted(root.glob(LOCALCONFIG_PATTERN)):
            unique.setdefault(config.resolve(), config)
    return tuple(unique.values())


def _backup(config: Path, backups: Path) -> Path:
    user = config.parent.parent.name
    copy = backups / user / config.name
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config, copy)
    return copy


def _write_atomically(config: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w", dir=config.parent, prefix=".omamods-", delete=False, encoding="utf-8"
    ) as stream:
        stream.write(text)
    shutil.copymode(config, stream.name)
    os.replace(stream.name, config)


def save_launch_options(
    configs: tuple[Path, ...], app_id: str, line: str, backups: Path
) -> tuple[Path, ...]:
    """Write every user that lists the app; e.g. ``save_launch_options(paths, '287700', line, folder)``.

    Each file is copied to ``backups/<user id>/`` first.
    """
    written: list[Path] = []
    errors: list[str] = []
    for config in configs:
        try:
            edited = set_launch_options(
                config.read_text(encoding="utf-8"), app_id, line
            )
        except ValueError as error:
            errors.append(str(error))
            continue  # Another Steam user may not own the game.
        _backup(config, backups)
        _write_atomically(config, edited)
        written.append(config)
    if not written:
        raise ValueError(
            f"Steam configs={[str(c) for c in configs]!r}: expected one listing "
            f"app {app_id} ({'; '.join(errors) or 'none found'})"
        )
    return tuple(written)


def backup_folder(storage_root: Path, now: datetime) -> Path:
    """Name this save's backup folder; e.g. ``backup_folder(root, datetime.now())``."""
    stamp = now.strftime("%Y%m%dT%H%M%S")
    return storage_root / "backups" / "steam-localconfig" / stamp
