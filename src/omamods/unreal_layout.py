"""Recognise an installed Unreal Engine game from its Content/Paks folder."""

from dataclasses import dataclass
from pathlib import Path

from omamods.filesystem import ReadableFiles

# Most games keep <Project>/Content/Paks at the root; collections such as
# KINGDOM HEARTS HD 2.8 nest each game one folder deeper.
PAK_PATTERNS = ("*/Content/Paks/*.pak", "*/*/Content/Paks/*.pak")


@dataclass(frozen=True)
class UnrealLayout:
    """Where an Unreal game's paks live and which mod files it can load."""

    paks_subpath: Path
    iostore: bool
    signed: bool


def _project_paks(install: Path, files: ReadableFiles) -> Path | None:
    for pattern in PAK_PATTERNS:
        folders = sorted({pak.parent for pak in files.glob(install, pattern)})
        # Engine/Content/Paks holds shared engine assets, never the game's.
        game = [f for f in folders if "Engine" not in f.relative_to(install).parts]
        if game:
            return game[0]
    return None


def detect_unreal_layout(install: Path, files: ReadableFiles) -> UnrealLayout | None:
    """Spot an Unreal game; e.g. ``detect_unreal_layout(Path('/g/Remnant2'), files)``."""
    paks = _project_paks(install, files)
    if paks is None:
        return None
    return UnrealLayout(
        paks.relative_to(install),
        bool(files.glob(paks, "*.utoc")),
        bool(files.glob(paks, "*.sig")),
    )
