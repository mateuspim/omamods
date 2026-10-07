"""Walk the site's download popups one file at a time, per mod.

Nexus' files tab opens the 'Mod Manager Download' popup only for the file in
its URL, so after each arrival the window must move on to the next file.
"""

from collections.abc import Collection
from dataclasses import dataclass, field

STAY = "stay"
NEXT = "next"
FINISHED = "finished"


@dataclass(frozen=True)
class BrowserStep:
    """What to do with a mod's window after checking staging."""

    action: str
    url: str | None = None
    unexpected: tuple[int, ...] = ()


@dataclass
class BrowserQueue:
    """Ordered (file ID, popup URL) pairs per (game, mod); e.g. ``BrowserQueue()``."""

    pending: dict[tuple[str, int], list[tuple[int, str]]] = field(default_factory=dict)
    # Files staged before or besides the request, so surprise arrivals stand out.
    known: dict[tuple[str, int], set[int]] = field(default_factory=dict)

    def add(
        self,
        game_id: str,
        mod_id: int,
        file_id: int,
        url: str,
        staged: Collection[int] = (),
    ) -> bool:
        """Queue a file; True when its popup should open now. E.g. ``q.add('sb', 1, 7, u)``."""
        self.known.setdefault((game_id, mod_id), set()).update(staged)
        queue = self.pending.setdefault((game_id, mod_id), [])
        if any(queued == file_id for queued, _ in queue):
            return False
        queue.append((file_id, url))
        return len(queue) == 1

    def advance(
        self, game_id: str, mod_id: int, staged: Collection[int]
    ) -> BrowserStep:
        """Drop arrived files; e.g. ``q.advance('sb', 1, {7})``."""
        key = (game_id, mod_id)
        queue = self.pending.get(key, [])
        unexpected = self._unexpected(key, queue, staged)
        remaining = [(file_id, url) for file_id, url in queue if file_id not in staged]
        if remaining == queue:
            return BrowserStep(STAY, unexpected=unexpected)
        if not remaining:
            del self.pending[key]
            self.known.pop(key, None)
            return BrowserStep(FINISHED, unexpected=unexpected)
        self.pending[key] = remaining
        # Only move the window on if the file it shows has arrived.
        if queue[0][0] not in staged:
            return BrowserStep(STAY, unexpected=unexpected)
        return BrowserStep(NEXT, remaining[0][1], unexpected)

    def _unexpected(
        self,
        key: tuple[str, int],
        queue: list[tuple[int, str]],
        staged: Collection[int],
    ) -> tuple[int, ...]:
        known = self.known.setdefault(key, set())
        requested = {file_id for file_id, _ in queue}
        surprise = tuple(sorted(set(staged) - known - requested))
        known.update(surprise)
        return surprise

    def waiting_for(self, game_id: str, mod_id: int) -> int | None:
        """The file the window shows now; e.g. ``q.waiting_for('sb', 1)``."""
        queue = self.pending.get((game_id, mod_id))
        return queue[0][0] if queue else None

    def waiting_url(self, game_id: str, mod_id: int) -> str | None:
        """The popup the window shows now; e.g. ``q.waiting_url('sb', 1)``."""
        queue = self.pending.get((game_id, mod_id))
        return queue[0][1] if queue else None

    def waiting_files(self) -> dict[tuple[str, int], int]:
        """Each mod's shown file; e.g. ``q.waiting_files() == {('sb', 1): 7}``."""
        return {key: queue[0][0] for key, queue in self.pending.items() if queue}
