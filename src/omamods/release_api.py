"""Read a repository's newest release from the Codeberg (Gitea) or GitHub API.

Both answer ``/repos/<owner>/<repo>/releases/latest`` with ``tag_name``,
``published_at``, and ``assets`` holding ``id``, ``name``, ``size``, and
``browser_download_url``. The transport sends no credentials: the Nexus API
key must never reach another site.
"""

from dataclasses import dataclass
from datetime import datetime
from http.client import HTTPException
import json
from pathlib import PurePosixPath
from typing import BinaryIO, Protocol
from urllib import error, parse, request

from omamods.cdn_download import (
    USER_AGENT,
    NexusHttpError,
    ProgressCallback,
    stream_download,
)
from omamods.nexus_api import NexusFile
from omamods.release_sources import ReleaseSource

ARCHIVE_SUFFIXES = frozenset({".zip", ".7z", ".rar"})
RELEASE_FILE_CATEGORY = "MAIN"


class ReleaseTransport(Protocol):
    """Inject HTTP so tests never contact Codeberg or GitHub."""

    def get_json(self, url: str) -> object:
        """Read API metadata; e.g. ``transport.get_json(source.latest_release_url)``."""
        ...

    def download(
        self,
        url: str,
        destination: BinaryIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Stream an asset from a byte offset; e.g. ``transport.download(url, f)``."""
        ...


class UrlReleaseTransport:
    """Call the forge APIs anonymously over HTTPS; e.g. ``UrlReleaseTransport()``."""

    def get_json(self, url: str) -> object:
        """Fetch JSON; for example, ``transport.get_json(url)``."""
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        try:
            with request.urlopen(
                request.Request(url, headers=headers), timeout=30
            ) as reply:
                return json.load(reply)
        except error.HTTPError as failure:
            raise NexusHttpError(failure.code, "a release listing") from failure
        except (error.URLError, HTTPException) as failure:
            raise ValueError(
                f"release API={url!r}: expected a reply ({failure})"
            ) from failure

    def download(
        self,
        url: str,
        destination: BinaryIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Stream a release asset; for example, ``transport.download(url, file)``."""
        stream_download(url, destination, progress, resume_from)


@dataclass(frozen=True)
class ReleaseAsset:
    """A downloadable archive of a release, described like a Nexus file."""

    file: NexusFile
    url: str


@dataclass(frozen=True)
class LatestRelease:
    """The newest release's tag and its archives."""

    tag: str
    assets: tuple[ReleaseAsset, ...]


def _text(value: dict[str, object], key: str) -> str:
    found = value.get(key)
    if not isinstance(found, str) or not found:
        raise ValueError(f"release field {key}={found!r}: expected a nonempty string")
    return found


def _number(value: dict[str, object], key: str) -> int:
    found = value.get(key)
    if not isinstance(found, int) or isinstance(found, bool) or found < 0:
        raise ValueError(f"release field {key}={found!r}: expected a whole number")
    return found


def _timestamp(published: str) -> int:
    try:
        return int(datetime.fromisoformat(published).timestamp())
    except ValueError as failure:
        raise ValueError(
            f"release published_at={published!r}: expected an ISO 8601 time"
        ) from failure


def _https_url(url: str) -> str:
    if parse.urlparse(url).scheme != "https":
        raise ValueError(f"release asset URL={url!r}: expected https://")
    return url


def _asset(value: object, tag: str, published: int) -> ReleaseAsset | None:
    if not isinstance(value, dict):
        raise ValueError(f"release asset={value!r}: expected an object")
    name = _text(value, "name")
    if PurePosixPath(name).suffix.lower() not in ARCHIVE_SUFFIXES:
        return None  # Checksums and signatures beside the archive.
    url = _https_url(_text(value, "browser_download_url"))
    size_kb = _number(value, "size") // 1024
    file_id = _number(value, "id")
    file = NexusFile(
        file_id, name, RELEASE_FILE_CATEGORY, published, name, tag, size_kb
    )
    return ReleaseAsset(file, url)


def parse_latest_release(value: object, source: ReleaseSource) -> LatestRelease:
    """Validate an API reply; e.g. ``parse_latest_release(reply, mgsvfix)``."""
    if not isinstance(value, dict):
        raise ValueError(f"{source.page_url} release={value!r}: expected an object")
    tag = _text(value, "tag_name")
    published = _timestamp(_text(value, "published_at"))
    listed = value.get("assets")
    if not isinstance(listed, list):
        raise ValueError(f"release field assets={listed!r}: expected a list")
    found = (_asset(item, tag, published) for item in listed)
    assets = tuple(asset for asset in found if asset is not None)
    if not assets:
        raise ValueError(
            f"{source.page_url} release {tag}: expected a .zip, .7z, or .rar asset"
        )
    return LatestRelease(tag, assets)


def fetch_latest_release(
    transport: ReleaseTransport, source: ReleaseSource
) -> LatestRelease:
    """Ask the forge; e.g. ``fetch_latest_release(UrlReleaseTransport(), mgsvfix)``."""
    return parse_latest_release(transport.get_json(source.latest_release_url), source)
