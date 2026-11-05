"""Set aside mod files no install record owns, keeping a way back.

Files move to a dated folder with a manifest of their original paths instead
of being deleted, so a wrongly flagged file (an official RE Engine patch that
looks like a mod) can be put back by hand.
"""

import json
from collections.abc import Mapping
from pathlib import Path
import shutil

MANIFEST = "moved.json"


def set_aside(
    found: Mapping[str, tuple[Path, ...]], destination: Path
) -> tuple[int, Path]:
    """Move files out of the games; e.g. ``set_aside({'re7': (patch,)}, root / 'removed' / 'now')``."""
    moved: dict[str, str] = {}
    for key, files in found.items():
        for index, file in enumerate(files):
            target = destination / key / f"{index:03d}-{file.name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file), str(target))
            moved[str(target)] = str(file)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / MANIFEST).write_text(json.dumps(moved, indent=2), encoding="utf-8")
    return len(moved), destination


def describe_found(
    found: Mapping[str, tuple[Path, ...]], names: Mapping[str, str]
) -> str:
    """List what would move; e.g. ``describe_found({'re7': (patch,)}, {'re7': 'RE7'})``."""
    lines = []
    for key, files in found.items():
        lines.append(f"{names.get(key, key)}: {len(files)} file(s)")
        lines.extend(f"    {file.name}" for file in files[:5])
        if len(files) > 5:
            lines.append(f"    … and {len(files) - 5} more")
    lines.append(
        "Files move to a 'removed' folder in OmaMods storage, not deleted. "
        "RE Engine official patches look the same as mod patches; if the game "
        "breaks, move them back or verify the game files in Steam."
    )
    return "\n".join(lines)
