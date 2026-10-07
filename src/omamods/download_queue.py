"""A download queue shared across processes through small JSON status files.

The TUI and the browser's nxm handler (a separate process) both write
``<storage-root>/downloads/<game>-<mod>-<file>.json``; the TUI's downloads
screen reads them to show progress, speed, and stalls.
"""

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import time
import uuid
from typing import Callable

from omamods.cdn_download import RetryPolicy
from omamods.nexus_api import NexusFile

QUEUED = "queued"
WAITING_FOR_BROWSER = "waiting for browser"
DOWNLOADING = "downloading"
DONE = "done"
FAILED = "failed"
STALLED = "stalled"
FINISHED_STATES = frozenset({DONE, FAILED})
STALL_SECONDS = 20.0
RETRY_ATTEMPTS = RetryPolicy().attempts
WRITE_INTERVAL_SECONDS = 0.5
RATE_WINDOW_SECONDS = 1.0
Clock = Callable[[], float]


@dataclass(frozen=True)
class DownloadStatus:
    """One file's place in the queue, as last written by its downloader."""

    game_id: str
    mod_id: int
    file_id: int
    file_name: str
    state: str
    received: int
    total: int | None
    bytes_per_second: float
    started: float
    updated: float
    progressed: float
    attempt: str = ""
    error: str = ""

    @property
    def key(self) -> str:
        """Name the status file; for example, ``status.key``."""
        return f"{self.game_id}-{self.mod_id}-{self.file_id}"


def shown_state(status: DownloadStatus, now: float) -> str:
    """Flag downloads with no new bytes recently; e.g. ``shown_state(s, time.time())``."""
    # A crashed handler process also leaves "downloading" behind; it shows as stalled.
    if status.state == DOWNLOADING and now - status.progressed > STALL_SECONDS:
        return STALLED
    return status.state


class DownloadLog:
    """Read and write the queue folder; e.g. ``DownloadLog(root / 'downloads')``."""

    def __init__(self, folder: Path, clock: Clock = time.time) -> None:
        self.folder = folder
        self.clock = clock

    def write(self, status: DownloadStatus) -> None:
        """Replace one entry atomically; for example, ``log.write(status)``."""
        self.folder.mkdir(parents=True, exist_ok=True)
        partial = self.folder / f".{status.key}.partial"
        partial.write_text(json.dumps(asdict(status)), encoding="utf-8")
        partial.replace(self.folder / f"{status.key}.json")

    def _current(self, key: str) -> DownloadStatus | None:
        try:
            text = (self.folder / f"{key}.json").read_text("utf-8")
            return DownloadStatus(**json.loads(text))
        except (OSError, TypeError, ValueError):
            return None

    def update(self, status: DownloadStatus) -> bool:
        """Write unless a retry replaced this attempt; e.g. ``log.update(status)``."""
        # A stalled attempt can wake up after a retry; it must not hide the retry.
        current = self._current(status.key)
        if current is not None and current.attempt != status.attempt:
            return False
        self.write(status)
        return True

    def begin(
        self, game_id: str, mod_id: int, file: NexusFile, state: str
    ) -> DownloadStatus:
        """Record a new attempt; e.g. ``log.begin('stellar-blade', 1, file, QUEUED)``."""
        now = self.clock()
        total = file.size_kb * 1024 if file.size_kb else None
        status = DownloadStatus(
            game_id,
            mod_id,
            file.file_id,
            file.file_name,
            state,
            0,
            total,
            0.0,
            now,
            now,
            now,
            uuid.uuid4().hex,
        )
        self.write(status)
        return status

    def finish(self, status: DownloadStatus, error: str | None) -> None:
        """Mark done or failed; for example, ``log.finish(status, None)``."""
        state = FAILED if error else DONE
        self.update(
            replace(status, state=state, updated=self.clock(), error=error or "")
        )

    def statuses(self) -> tuple[DownloadStatus, ...]:
        """List entries, newest first; for example, ``log.statuses()``."""
        found: list[DownloadStatus] = []
        for path in self.folder.glob("*.json"):
            try:
                found.append(DownloadStatus(**json.loads(path.read_text("utf-8"))))
            except (OSError, TypeError, ValueError):
                continue  # Skip entries another process is mid-way through writing.
        return tuple(sorted(found, key=lambda status: status.started, reverse=True))

    def clear_finished(self) -> int:
        """Forget done and failed entries; for example, ``log.clear_finished()``."""
        finished = [s for s in self.statuses() if s.state in FINISHED_STATES]
        for status in finished:
            (self.folder / f"{status.key}.json").unlink(missing_ok=True)
        return len(finished)


class ProgressRecorder:
    """Feed transport progress into the queue, writing at most twice a second."""

    def __init__(self, log: DownloadLog, status: DownloadStatus) -> None:
        now = log.clock()
        self.log = log
        self.status = replace(status, state=DOWNLOADING, updated=now, progressed=now)
        self.sample = (now, 0)
        self.written = 0.0
        log.update(self.status)

    def note_retry(self, attempt: int, failure: BaseException) -> None:
        """Show a retry instead of a failure; e.g. ``recorder.note_retry(1, error)``."""
        now = self.log.clock()
        # Counting the retry as progress keeps the backoff wait from looking stalled.
        self.status = replace(
            self.status,
            error=f"retrying {attempt + 1}/{RETRY_ATTEMPTS} after: {failure}",
            updated=now,
            progressed=now,
        )
        self.log.update(self.status)

    def __call__(self, received: int, total: int | None) -> None:
        """Record bytes so far; for example, ``recorder(1024, 4096)``."""
        now = self.log.clock()
        rate = self.status.bytes_per_second
        if now - self.sample[0] >= RATE_WINDOW_SECONDS:
            # max(0, ...): a restart after an ignored Range header drops the count.
            rate = max(0.0, (received - self.sample[1]) / (now - self.sample[0]))
            self.sample = (now, received)
        moved = received != self.status.received
        self.status = replace(
            self.status,
            received=received,
            total=total or self.status.total,
            bytes_per_second=rate,
            updated=now,
            progressed=now if moved else self.status.progressed,
            error="" if moved else self.status.error,
        )
        if now - self.written >= WRITE_INTERVAL_SECONDS:
            self.written = now
            self.log.update(self.status)
