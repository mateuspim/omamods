"""Stream files from Nexus' CDN: resumable requests, progress, and retries.

Kept apart from the API client because CDN links are pre-signed and need no
key, but do need retrying: Stellar Blade mod 533's fifth archive failed with
'Connection reset by peer' before any byte arrived.
"""

from collections.abc import Callable
from dataclasses import dataclass
from http.client import HTTPException, InvalidURL
import time
from typing import BinaryIO, Protocol
from urllib import error, parse, request

VERSION = "0.1.0"
COPY_CHUNK_BYTES = 256 * 1024
# Nexus' image CDN answers 403 to urllib's default "Python-urllib" agent.
USER_AGENT = f"OmaMods/{VERSION}"
# Called with (bytes received so far, total bytes if the server said).
ProgressCallback = Callable[[int, int | None], None]
TRANSIENT_HTTP_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class NexusHttpError(ValueError):
    """An HTTP failure whose status decides the next step (403: not Premium)."""

    def __init__(self, code: int, expected: str) -> None:
        super().__init__(f"Nexus HTTP {code}: expected {expected}")
        self.code = code


class TransientDownloadError(OSError):
    """A dropped connection or timeout that a retry can fix."""


def is_transient(failure: BaseException) -> bool:
    """Decide whether retrying can help; e.g. ``is_transient(NexusHttpError(503, ''))``."""
    if isinstance(failure, NexusHttpError):
        return failure.code in TRANSIENT_HTTP_CODES
    return isinstance(failure, TransientDownloadError)


def encoded_download_url(url: str) -> str:
    """Escape raw spaces Nexus CDN links can contain; e.g. ``encoded_download_url(u)``."""
    # Some CDN links arrive unescaped ('/100/Sample Outfit-100.rar'),
    # which urllib rejects. Keep existing %XX escapes and URL delimiters intact.
    parts = parse.urlsplit(url)
    path = parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = parse.quote(parts.query, safe="=&%:@!$'()*+,;/?-._~")
    return parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def download_request(url: str, resume_from: int = 0) -> request.Request:
    """Build a CDN request; e.g. ``download_request('https://staticdelivery...', 0)``."""
    headers = {"User-Agent": USER_AGENT}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
    return request.Request(encoded_download_url(url), headers=headers)


def content_length(header: str | None) -> int | None:
    """Parse Content-Length; for example, ``content_length('12') == 12``."""
    return int(header) if header and header.isdecimal() else None


def copy_with_progress(
    source: BinaryIO,
    destination: BinaryIO,
    total: int | None,
    progress: ProgressCallback | None,
    start: int = 0,
) -> int:
    """Copy in chunks, reporting running bytes; e.g. ``copy_with_progress(a, b, None, None)``."""
    received = start
    while chunk := source.read(COPY_CHUNK_BYTES):
        destination.write(chunk)
        received += len(chunk)
        if progress is not None:
            progress(received, total)
    return received


def copy_response(
    response: BinaryIO,
    status: int,
    length: str | None,
    destination: BinaryIO,
    progress: ProgressCallback | None,
    resume_from: int,
) -> None:
    """Copy a reply, restarting if a Range was ignored; e.g. ``copy_response(r, 200, '9', f, None, 0)``."""
    if resume_from and status != 206:
        # The server ignored the Range header and sent the whole file again.
        destination.seek(0)
        destination.truncate()
        resume_from = 0
    remaining = content_length(length)
    total = remaining + resume_from if remaining is not None else None
    copy_with_progress(response, destination, total, progress, resume_from)


def stream_download(
    url: str,
    destination: BinaryIO,
    progress: ProgressCallback | None,
    resume_from: int,
) -> None:
    """Fetch over HTTPS; e.g. ``stream_download(uri, file, None, 0)``."""
    try:
        with request.urlopen(download_request(url, resume_from), timeout=60) as reply:
            length = reply.headers.get("Content-Length")
            copy_response(
                reply, reply.status, length, destination, progress, resume_from
            )
    except error.HTTPError as failure:
        raise NexusHttpError(failure.code, "a downloadable file") from failure
    except InvalidURL as failure:
        raise ValueError(
            f"Nexus download: expected a valid URL ({failure})"
        ) from failure
    except (error.URLError, HTTPException, ConnectionError, TimeoutError) as failure:
        reason = getattr(failure, "reason", failure)
        raise TransientDownloadError(
            f"Nexus download interrupted: {reason}"
        ) from failure


class ResumableTransport(Protocol):
    """The part of a transport retries need."""

    def download(
        self,
        url: str,
        destination: BinaryIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Stream from ``resume_from``; e.g. ``transport.download(u, f, None, 0)``."""
        ...


@dataclass(frozen=True)
class RetryPolicy:
    """How often and how patiently to retry; e.g. ``RetryPolicy(attempts=5)``."""

    attempts: int = 5
    first_delay_seconds: float = 2.0
    sleep: Callable[[float], None] = time.sleep
    on_retry: Callable[[int, BaseException], None] | None = None

    def delay(self, attempt: int) -> float:
        """Back off exponentially; for example, ``policy.delay(2) == 4.0``."""
        return self.first_delay_seconds * 2 ** (attempt - 1)


def download_with_retries(
    transport: ResumableTransport,
    url: str,
    destination: BinaryIO,
    progress: ProgressCallback | None,
    policy: RetryPolicy,
) -> None:
    """Retry transient failures, resuming; e.g. ``download_with_retries(t, u, f, None, p)``."""
    for attempt in range(1, policy.attempts + 1):
        try:
            transport.download(url, destination, progress, destination.tell())
            return
        except Exception as failure:
            if attempt == policy.attempts or not is_transient(failure):
                raise
            if policy.on_retry is not None:
                policy.on_retry(attempt, failure)
            policy.sleep(policy.delay(attempt))
