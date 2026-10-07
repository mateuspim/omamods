"""Small project-owned boundary around Nexus' personal-use v1 API."""

from dataclasses import dataclass
from http.client import HTTPException
import json
from pathlib import Path
import re
from typing import BinaryIO, Protocol
from urllib import error, parse, request

from omamods.cdn_download import (
    USER_AGENT,
    VERSION,
    NexusHttpError,
    ProgressCallback,
    stream_download,
)

API_ROOT = "https://api.nexusmods.com/v1"


@dataclass(frozen=True)
class NexusPage:
    """Canonical Nexus game domain and numeric mod ID."""

    domain: str
    mod_id: int


@dataclass(frozen=True)
class NexusFile:
    """A selectable archive in a mod's file listing."""

    file_id: int
    file_name: str
    category: str
    uploaded_timestamp: int
    display_name: str = ""
    version: str = ""
    size_kb: int = 0


def describe_nexus_file(file: NexusFile) -> str:
    """Name a file for people; e.g. ``describe_nexus_file(f) == 'Hair 1.0 (OPTIONAL)'``."""
    name = file.display_name or file.file_name
    version = f" {file.version}" if file.version else ""
    return f"{name}{version} ({file.category})"


@dataclass(frozen=True)
class NexusModInfo:
    """Page details shown before choosing files to stage."""

    name: str
    summary: str
    author: str
    version: str
    picture_url: str | None


@dataclass(frozen=True)
class NxmAuthorization:
    """Short-lived per-file authorization for non-premium accounts."""

    domain: str
    mod_id: int
    file_id: int
    key: str
    expires: int


class NexusTransport(Protocol):
    """Inject HTTP so tests cannot contact or download from Nexus."""

    def get_json(self, url: str, api_key: str) -> object:
        """Read metadata; for example, ``transport.get_json(url, key)``."""
        ...

    def download(
        self,
        url: str,
        destination: BinaryIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Stream an archive from a byte offset; e.g. ``transport.download(uri, file)``."""
        ...


class UrlNexusTransport:
    """Use HTTPS and identify this personal-use client to the Nexus API."""

    def get_json(self, url: str, api_key: str) -> object:
        """Fetch JSON with a private key; for example, ``client.get_json(url, key)``."""
        headers = {
            "apikey": api_key,
            "Application-Name": "OmaMods",
            "Application-Version": VERSION,
            "User-Agent": USER_AGENT,
        }
        try:
            with request.urlopen(
                request.Request(url, headers=headers), timeout=30
            ) as response:
                return json.load(response)
        except error.HTTPError as failure:
            raise NexusHttpError(failure.code, "a successful API response") from failure
        except HTTPException as failure:
            raise ValueError(
                f"Nexus API: expected valid HTTP ({failure!r})"
            ) from failure

    def download(
        self,
        url: str,
        destination: BinaryIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Stream signed CDN content; for example, ``client.download(uri, file)``."""
        stream_download(url, destination, progress, resume_from)


def parse_nexus_page(url: str) -> NexusPage:
    """Accept a mod page; e.g. ``parse_nexus_page('https://www.nexusmods.com/cronosthenewdawn/mods/38')``."""
    parsed = parse.urlparse(url)
    match = re.fullmatch(r"/([a-z0-9]+)/mods/([1-9][0-9]*)/?", parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "www.nexusmods.com" or not match:
        raise ValueError(
            f"Nexus page={url!r}: expected https://www.nexusmods.com/<game>/mods/<id>"
        )
    return NexusPage(match.group(1), int(match.group(2)))


def parse_nxm_link(url: str) -> NxmAuthorization:
    """Parse site-issued access; e.g. ``parse_nxm_link('nxm://game/mods/1/files/2?key=x&expires=3')``."""
    parsed = parse.urlparse(url)
    match = re.fullmatch(r"/mods/([1-9][0-9]*)/files/([1-9][0-9]*)", parsed.path)
    query = parse.parse_qs(parsed.query, strict_parsing=True)
    key, expiry = query.get("key", []), query.get("expires", [])
    if not _valid_nxm_shape(parsed.scheme, parsed.hostname, match, key, expiry):
        raise ValueError(
            "NXM link: expected nxm://<game>/mods/<id>/files/<id>?key=...&expires=..."
        )
    if not expiry[0].isascii() or not expiry[0].isdecimal():
        raise ValueError(f"NXM expiry={expiry[0]!r}: expected Unix seconds")
    return NxmAuthorization(
        parsed.hostname,
        int(match.group(1)),
        int(match.group(2)),
        key[0],
        int(expiry[0]),
    )


def _valid_nxm_shape(
    scheme: str,
    domain: str | None,
    match: re.Match[str] | None,
    keys: list[str],
    expiries: list[str],
) -> bool:
    return (
        scheme == "nxm" and bool(domain and match) and len(keys) == len(expiries) == 1
    )


def _nexus_file(value: object) -> NexusFile:
    if not isinstance(value, dict):
        raise ValueError(f"Nexus file={value!r}: expected an object")
    base = _base_file(value)
    return NexusFile(
        base.file_id,
        base.file_name,
        base.category,
        base.uploaded_timestamp,
        _text(value, "name"),
        _text(value, "version"),
        _count(value, "size_kb"),
    )


def _base_file(value: dict[str, object]) -> NexusFile:
    file_id, name = value.get("file_id"), value.get("file_name")
    category, uploaded = value.get("category_name"), value.get("uploaded_timestamp", 0)
    if (
        type(file_id) is not int
        or file_id <= 0
        or not isinstance(name, str)
        or not name
    ):
        raise ValueError(
            f"Nexus file={value!r}: expected positive file_id and file_name"
        )
    if not isinstance(category, str) or type(uploaded) is not int:
        raise ValueError(
            f"Nexus file={value!r}: expected category_name and uploaded_timestamp"
        )
    if Path(name).name != name or name in (".", "..") or "\\" in name or "\0" in name:
        raise ValueError(f"Nexus file_name={name!r}: expected a plain archive filename")
    return NexusFile(file_id, name, category, uploaded)


def _text(value: dict[str, object], key: str) -> str:
    field = value.get(key)
    return field if isinstance(field, str) else ""


def _count(value: dict[str, object], key: str) -> int:
    field = value.get(key)
    return field if type(field) is int and field > 0 else 0


def _picture_url(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if parse.urlparse(value).scheme != "https":
        raise ValueError(f"Nexus picture_url={value!r}: expected an HTTPS URL")
    return value


def parse_mod_info(value: object) -> NexusModInfo:
    """Validate mod details; for example, ``parse_mod_info({'name': 'Suit'})``."""
    if not isinstance(value, dict) or not isinstance(value.get("name"), str):
        raise ValueError(f"Nexus mod={value!r}: expected an object with a name")
    return NexusModInfo(
        value["name"],
        _text(value, "summary"),
        _text(value, "author"),
        _text(value, "version"),
        _picture_url(value.get("picture_url")),
    )


def parse_file_listing(value: object) -> tuple[NexusFile, ...]:
    """Validate metadata; for example, ``parse_file_listing({'files': []})``."""
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        raise ValueError(f"Nexus response={value!r}: expected a files array")
    return tuple(_nexus_file(entry) for entry in value["files"])


def select_file(files: tuple[NexusFile, ...], requested_id: int | None) -> NexusFile:
    """Select one archive; for example, ``select_file(files, 123)``."""
    selected = (
        tuple(item for item in files if item.file_id == requested_id)
        if requested_id
        else tuple(item for item in files if item.category == "MAIN")
    )
    if len(selected) != 1:
        raise ValueError(
            f"file_id={requested_id!r}: expected one file; available MAIN IDs are {[item.file_id for item in files if item.category == 'MAIN']!r}"
        )
    return selected[0]


def parse_download_links(value: object) -> str:
    """Require one signed HTTPS link; for example, ``parse_download_links([{'URI': url}])``."""
    if not isinstance(value, list) or not value or not isinstance(value[0], dict):
        raise ValueError("Nexus download response: expected a nonempty link list")
    uri = value[0].get("URI")
    parsed = parse.urlparse(uri) if isinstance(uri, str) else None
    if not parsed or parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Nexus download URI: expected an HTTPS link")
    return uri


class NexusApi:
    """Fetch a chosen file without scraping mod pages or bypassing account limits."""

    def __init__(self, transport: NexusTransport, api_key: str) -> None:
        self.transport = transport
        self.api_key = api_key

    def mod_info(self, page: NexusPage) -> NexusModInfo:
        """Read page details; for example, ``api.mod_info(page)``."""
        url = f"{API_ROOT}/games/{page.domain}/mods/{page.mod_id}.json"
        return parse_mod_info(self.transport.get_json(url, self.api_key))

    def files(self, page: NexusPage) -> tuple[NexusFile, ...]:
        """List uploaded archives; for example, ``api.files(page)``."""
        url = f"{API_ROOT}/games/{page.domain}/mods/{page.mod_id}/files.json"
        return parse_file_listing(self.transport.get_json(url, self.api_key))

    def download_url(
        self, page: NexusPage, file: NexusFile, nxm: NxmAuthorization | None
    ) -> str:
        """Resolve authorized CDN URL; for example, ``api.download_url(page, file, None)``."""
        url = f"{API_ROOT}/games/{page.domain}/mods/{page.mod_id}/files/{file.file_id}/download_link.json"
        if nxm:
            if (nxm.domain, nxm.mod_id, nxm.file_id) != (
                page.domain,
                page.mod_id,
                file.file_id,
            ):
                raise ValueError(
                    "NXM link: expected the selected Nexus game, mod, and file IDs"
                )
            url += "?" + parse.urlencode({"key": nxm.key, "expires": nxm.expires})
        return parse_download_links(self.transport.get_json(url, self.api_key))
