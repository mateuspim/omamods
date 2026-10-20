"""Read which packages each installed mod's containers carry.

Ownership records already list every file an install created, so the
containers come from them; only each container's index is read, never the
whole .ucas or a multi-gigabyte .pak.
"""

from collections.abc import Callable, Iterable
import json
from pathlib import Path, PurePosixPath

from omamods.asset_collisions import ModContainer, container_entries
from omamods.byte_ranges import ByteRanges
from omamods.iostore_index import toc_asset_paths
from omamods.pak_index import pak_asset_paths

OpenRanges = Callable[[Path], ByteRanges]
INDEX_READERS: dict[str, Callable[[ByteRanges], tuple[str, ...]]] = {
    ".utoc": toc_asset_paths,
    ".pak": pak_asset_paths,
}


def recorded_containers(record: Path) -> tuple[Path, ...]:
    """List a record's .utoc/.pak files; e.g. ``recorded_containers(state)``."""
    try:
        state = json.loads(record.read_text(encoding="utf-8"))
        paks = Path(state["paks"])
        relative = [str(asset["relative_path"]) for asset in state["assets"]]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"install state={str(record)!r}: expected paks and assets[].relative_path"
        ) from error
    return tuple(
        paks / path
        for path in relative
        if PurePosixPath(path).suffix.lower() in INDEX_READERS
        and ".." not in PurePosixPath(path).parts
    )


class ContainerIndexes:
    """Read container indexes once per file version; e.g. ``ContainerIndexes(FileRanges)``."""

    def __init__(self, open_ranges: OpenRanges) -> None:
        self.open_ranges = open_ranges
        self.cache: dict[tuple[Path, int], tuple[str, ...]] = {}

    def paths(self, container: Path) -> tuple[str, ...]:
        """What one file indexes; for example, ``indexes.paths(utoc)``."""
        ranges = self.open_ranges(container)
        # Reinstalls rewrite the file; its size is a cheap stand-in for a version.
        key = (container, ranges.size())
        if key not in self.cache:
            reader = INDEX_READERS[container.suffix.lower()]
            self.cache[key] = reader(ranges)
        return self.cache[key]

    def containers(self, owner: str, files: Iterable[Path]) -> tuple[ModContainer, ...]:
        """Group a mod's files by container; e.g. ``indexes.containers('Hero', files)``."""
        grouped: dict[Path, list[str]] = {}
        for path in files:
            # A stub .pak and its .utoc are one container under one name.
            grouped.setdefault(path.with_suffix(""), []).extend(self.paths(path))
        return tuple(
            ModContainer(owner, stem.name, container_entries(paths))
            for stem, paths in sorted(grouped.items())
        )
