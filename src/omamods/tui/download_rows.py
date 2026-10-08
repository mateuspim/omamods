"""Render download-queue entries for the queue screen and the mods-screen panel."""

from collections import Counter
from collections.abc import Callable

from omamods.download_queue import (
    DONE,
    DOWNLOADING,
    FAILED,
    QUEUED,
    STALLED,
    WAITING_FOR_BROWSER,
    DownloadStatus,
    shown_state,
)
from omamods.tui.service import ModsService

QUEUE_COLUMNS = (
    "State",
    "Mod",
    "File",
    "Progress",
    "Speed",
    "ETA",
    "Last data",
    "Error",
)
TitleLookup = Callable[[DownloadStatus], str]
RETRYABLE_STATES = frozenset({FAILED, STALLED, WAITING_FOR_BROWSER, QUEUED})
# The summary lists states in this order, busiest first.
SUMMARY_STATES = (DOWNLOADING, STALLED, WAITING_FOR_BROWSER, QUEUED, FAILED, DONE)


def human_bytes(count: float) -> str:
    """Format sizes; for example, ``human_bytes(1536) == '1.5 KB'``."""
    for unit in ("B", "KB", "MB", "GB"):
        if count < 1024 or unit == "GB":
            return f"{count:.0f} {unit}" if unit == "B" else f"{count:.1f} {unit}"
        count /= 1024
    return f"{count:.1f} GB"


def progress_text(status: DownloadStatus) -> str:
    """Show bytes and percent; e.g. ``progress_text(status)``."""
    if status.state == DONE:
        return human_bytes(status.received or status.total or 0)
    if not status.total:
        return human_bytes(status.received)
    percent = 100 * status.received / status.total
    return (
        f"{percent:.0f}%  {human_bytes(status.received)} / {human_bytes(status.total)}"
    )


def eta_text(status: DownloadStatus) -> str:
    """Estimate time left; for example, ``eta_text(status)``."""
    if status.state != DOWNLOADING or not status.total or status.bytes_per_second <= 0:
        return ""
    seconds = int((status.total - status.received) / status.bytes_per_second)
    return f"{seconds // 60}m {seconds % 60:02d}s"


def queue_cells(status: DownloadStatus, title: str, now: float) -> tuple[str, ...]:
    """Render one queue row; for example, ``queue_cells(status, 'Suit', now)``."""
    state = shown_state(status, now)
    active = status.state == DOWNLOADING
    return (
        state,
        title,
        status.file_name,
        progress_text(status),
        f"{human_bytes(status.bytes_per_second)}/s" if active else "",
        eta_text(status),
        f"{now - status.progressed:.0f}s ago" if active else "",
        status.error,
    )


def _active_text(status: DownloadStatus, title: str) -> str:
    percent = f" {100 * status.received / status.total:.0f}%" if status.total else ""
    return f"{title}{percent} · {human_bytes(status.bytes_per_second)}/s"


def active_download(
    statuses: tuple[DownloadStatus, ...], game_id: str, now: float
) -> DownloadStatus | None:
    """Pick a game's running download; e.g. ``active_download(s, 'sb', now)``."""
    running = (s for s in statuses if shown_state(s, now) == DOWNLOADING)
    return next((s for s in running if s.game_id == game_id), None)


def queue_summary(
    statuses: tuple[DownloadStatus, ...], game_id: str, titles: TitleLookup, now: float
) -> str:
    """Count every game's entries in one line; e.g. ``queue_summary(s, 'sb', t, now)``.

    The game's running download, if any, is named after the downloading count.
    """
    if not statuses:
        return "↓ Downloads: queue empty"
    counts = Counter(shown_state(status, now) for status in statuses)
    parts = [f"{counts[state]} {state}" for state in SUMMARY_STATES if counts[state]]
    active = active_download(statuses, game_id, now)
    if active is not None:
        parts[0] += f" ({_active_text(active, titles(active))})"
    return "↓ Downloads: " + " · ".join(parts)


class DownloadTitles:
    """Cache mod titles for queue rows; e.g. ``DownloadTitles(service)(status)``."""

    def __init__(self, service: ModsService) -> None:
        self.service = service
        self.titles: dict[tuple[str, int], str] = {}

    def __call__(self, status: DownloadStatus) -> str:
        key = (status.game_id, status.mod_id)
        if key not in self.titles:
            self.titles[key] = self._lookup(status)
        return self.titles[key]

    def _lookup(self, status: DownloadStatus) -> str:
        try:
            game = self.service.catalog.get(status.game_id)
            return self.service.staged_mod(game, status.mod_id).title
        except ValueError:
            return f"{status.game_id} mod {status.mod_id}"


def retry_outcome(service: ModsService, status: DownloadStatus) -> str | None:
    """Retry in a worker thread; a message when the site needs a click.

    Example: ``retry_outcome(service, status)``.
    """
    if service.retry(status):
        return None
    return f"{status.file_name}: click 'Mod Manager Download' on Nexus."
