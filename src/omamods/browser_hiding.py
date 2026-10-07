"""Decide when a mod's Nexus window can leave the screen, and when it must return.

After the user clicks 'Mod Manager Download', the nxm handler marks the file
``downloading``; the window has done its job until the next file needs a click.
If that download fails, the popup comes back so the user can click again.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from omamods.download_queue import DOWNLOADING, FAILED, DownloadStatus

ModKey = tuple[str, int]


def files_in_state(
    statuses: Iterable[DownloadStatus], state: str
) -> frozenset[tuple[str, int, int]]:
    """Index by (game, mod, file); e.g. ``files_in_state(log.statuses(), FAILED)``."""
    return frozenset(
        (status.game_id, status.mod_id, status.file_id)
        for status in statuses
        if status.state == state
    )


@dataclass
class HiddenWindows:
    """Remember which mods' windows are hidden; e.g. ``HiddenWindows()``."""

    hidden: set[ModKey] = field(default_factory=set)

    def to_hide(
        self, waiting: Mapping[ModKey, int], statuses: Iterable[DownloadStatus]
    ) -> tuple[ModKey, ...]:
        """Mods whose shown file started; e.g. ``h.to_hide({('sb', 1): 7}, s)``."""
        started = files_in_state(statuses, DOWNLOADING)
        keys = tuple(
            key
            for key, file_id in waiting.items()
            if key not in self.hidden and (*key, file_id) in started
        )
        self.hidden.update(keys)
        return keys

    def to_restore(
        self, waiting: Mapping[ModKey, int], statuses: Iterable[DownloadStatus]
    ) -> tuple[ModKey, ...]:
        """Hidden mods whose shown file failed; e.g. ``h.to_restore(w, s)``."""
        failed = files_in_state(statuses, FAILED)
        keys = tuple(
            key
            for key in sorted(self.hidden)
            if key in waiting and (*key, waiting[key]) in failed
        )
        self.hidden.difference_update(keys)
        return keys

    def forget(self, key: ModKey) -> None:
        """Drop a mod whose window closed; e.g. ``hidden.forget(('sb', 1))``."""
        self.hidden.discard(key)
