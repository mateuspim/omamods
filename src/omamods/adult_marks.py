"""Remember which mods are NSFW and how the mods list treats them.

Nexus flags adult mods itself; hand marks cover AyakaMods, hand-staged
archives, and mods Nexus got wrong. Kept in ``<storage>/adult_marks.json``::

    {"mode": "blur", "marks": {"stellar-blade": {"nexus:12": true, "ayaka:4": false}}}
"""

from dataclasses import dataclass, field, replace
import json
from pathlib import Path

ADULT_MARKS_FILE = "adult_marks.json"
SHOW, BLUR, HIDE = "show", "blur", "hide"
# H steps through these; blur comes first so NSFW pictures start covered.
ADULT_MODES = (BLUR, HIDE, SHOW)


@dataclass(frozen=True)
class AdultMarks:
    """The NSFW mode plus hand marks per game; e.g. ``AdultMarks(mode=HIDE)``."""

    mode: str = BLUR
    # game_id -> mod key ("nexus:12") -> True (NSFW) or False (not NSFW).
    marks: dict[str, dict[str, bool]] = field(default_factory=dict)


def is_adult(marks: AdultMarks, game_id: str, mod_key: str, flagged: bool) -> bool:
    """A hand mark beats the site's flag; e.g. ``is_adult(m, 'sb', 'nexus:1', True)``."""
    return marks.marks.get(game_id, {}).get(mod_key, flagged)


def with_mark(marks: AdultMarks, game_id: str, mod_key: str, adult: bool) -> AdultMarks:
    """Record a hand mark; e.g. ``with_mark(m, 'sb', 'ayaka:4', True)``."""
    game_marks = {**marks.marks.get(game_id, {}), mod_key: adult}
    return replace(marks, marks={**marks.marks, game_id: game_marks})


def next_mode(mode: str) -> str:
    """Step to the next mode, wrapping; e.g. ``next_mode(BLUR) == HIDE``."""
    return ADULT_MODES[(ADULT_MODES.index(mode) + 1) % len(ADULT_MODES)]


def _parse_mode(record: dict[str, object]) -> str:
    mode = record.get("mode")
    if mode in ADULT_MODES:
        return str(mode)
    # Files from before blur held only "hide": true or false.
    return HIDE if record.get("hide") is True else BLUR


def _parse_marks(value: object) -> dict[str, dict[str, bool]]:
    if not isinstance(value, dict):
        raise ValueError(f"marks={value!r}: expected {{game: {{mod key: bool}}}}")
    parsed: dict[str, dict[str, bool]] = {}
    for game_id, game_marks in value.items():
        if not isinstance(game_marks, dict):
            raise ValueError(f"marks[{game_id!r}]={game_marks!r}: expected an object")
        parsed[str(game_id)] = {str(k): v is True for k, v in game_marks.items()}
    return parsed


def load_adult_marks(root: Path) -> AdultMarks:
    """Read the saved marks, or none yet; e.g. ``load_adult_marks(storage_root)``."""
    path = root / ADULT_MARKS_FILE
    if not path.is_file():
        return AdultMarks()
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        return AdultMarks(_parse_mode(record), _parse_marks(record.get("marks", {})))
    except (AttributeError, ValueError) as error:
        raise ValueError(
            f"adult marks={str(path)!r}: expected {{'mode': {ADULT_MODES}, 'marks': {{...}}}}"
        ) from error


def save_adult_marks(root: Path, marks: AdultMarks) -> Path:
    """Write the marks atomically; e.g. ``save_adult_marks(storage_root, marks)``."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / ADULT_MARKS_FILE
    temporary = path.with_suffix(".json.partial")
    record = {"mode": marks.mode, "marks": marks.marks}
    temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path
