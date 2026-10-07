"""Recognise an installed RE Engine game from the base pak at its root."""

from pathlib import Path

from omamods.filesystem import ReadableFiles

BASE_PAK = "re_chunk_000.pak"
# Monster Hunter Wilds and later titles split the base into sub paks, and pak
# mods patch the first one: re_chunk_000.pak.sub_000.pak.patch_003.pak.
SUB_PAK = "re_chunk_000.pak.sub_000.pak"
PATCH_CHAINS = (SUB_PAK, BASE_PAK)


def detect_patch_chain(install: Path, files: ReadableFiles) -> str | None:
    """Name the pak mods patch; e.g. ``detect_patch_chain(Path('/g/RE7'), files)``."""
    names = {path.name for path in files.glob(install, f"{BASE_PAK}*")}
    return next((chain for chain in PATCH_CHAINS if chain in names), None)
