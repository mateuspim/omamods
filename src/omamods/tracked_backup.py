"""Keep a copy of tracked mod files before uninstalling them.

Uninstalling deletes a mod's files; "clean everything" promises a way back, so
each file is first linked, or copied across drives, into the removed folder
beside a manifest of where it came from, in the same shape set_aside writes.
"""

from collections.abc import Mapping
import json
import os
from pathlib import Path
import shutil

from omamods.untracked_clean import MANIFEST


def keep_copy(source: Path, target: Path) -> None:
    """Hard-link, else copy, one file; e.g. ``keep_copy(mod_pak, removed / 'a.pak')``."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        # A link costs no space and outlives the uninstall's unlink.
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def keep_copies(found: Mapping[str, tuple[Path, ...]], destination: Path) -> int:
    """Copy files aside with a manifest; e.g. ``keep_copies({'sb': (pak,)}, root / 'tracked')``."""
    kept: dict[str, str] = {}
    for key, files in found.items():
        for index, file in enumerate(f for f in files if f.is_file()):
            target = destination / key / f"{index:03d}-{file.name}"
            keep_copy(file, target)
            kept[str(target)] = str(file)
    if kept:
        destination.mkdir(parents=True, exist_ok=True)
        manifest = json.dumps(kept, indent=2)
        (destination / MANIFEST).write_text(manifest, encoding="utf-8")
    return len(kept)
