"""Read AyakaMods mod pages; downloads happen in the browser, which is logged in.

The site's download endpoint answers 403 without a session, and its API is not
public yet, so page details come from the JSON-LD block every mod page embeds.
"""

from dataclasses import dataclass
from http.client import HTTPException
import json
import re
from typing import Protocol
from urllib import error, parse, request

from omamods.cdn_download import USER_AGENT
from omamods.nexus_api import NexusModInfo

SITE_ROOT = "https://ayakamods.com"
SITE_HOSTS = frozenset({"ayakamods.com", "www.ayakamods.com"})
LD_JSON_BLOCK = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)
MOD_SUBCATEGORY = "Game Modification"


@dataclass(frozen=True)
class AyakaPage:
    """One mod on AyakaMods, by its numeric resource ID."""

    mod_id: int


@dataclass(frozen=True)
class AyakaModDetails:
    """Page details plus the game the page says the mod is for."""

    info: NexusModInfo
    game_name: str
    modified: str


class AyakaPageTransport(Protocol):
    """Inject HTTP so tests never contact AyakaMods."""

    def get_text(self, url: str) -> str:
        """Fetch a page as text; for example, ``transport.get_text(url)``."""
        ...


class UrlAyakaPageTransport:
    """Fetch public pages over HTTPS as OmaMods."""

    def get_text(self, url: str) -> str:
        """Fetch a page; for example, ``UrlAyakaPageTransport().get_text(url)``."""
        headers = {"User-Agent": USER_AGENT}
        try:
            with request.urlopen(
                request.Request(url, headers=headers), timeout=30
            ) as response:
                return response.read().decode("utf-8")
        except error.HTTPError as failure:
            raise ValueError(
                f"AyakaMods HTTP {failure.code} for {url!r}: expected a page"
            ) from failure
        except (HTTPException, UnicodeDecodeError) as failure:
            raise ValueError(
                f"AyakaMods page={url!r}: expected UTF-8 HTML ({failure!r})"
            ) from failure


def parse_ayaka_page(url: str) -> AyakaPage:
    """Accept a mod page; e.g. ``parse_ayaka_page('https://ayakamods.com/mods/sample.7322/')``."""
    parsed = parse.urlparse(url)
    # XenForo resource paths are '<slug>.<id>' or just '<id>', plus subpages.
    match = re.fullmatch(r"/mods/(?:[^/]*\.)?([1-9][0-9]*)(?:/.*)?", parsed.path)
    if parsed.scheme != "https" or parsed.hostname not in SITE_HOSTS or not match:
        raise ValueError(
            f"AyakaMods page={url!r}: expected https://ayakamods.com/mods/<name>.<id>/"
        )
    return AyakaPage(int(match.group(1)))


def is_ayaka_url(url: str) -> bool:
    """Tell AyakaMods links apart; e.g. ``is_ayaka_url('https://ayakamods.com/')``."""
    return parse.urlparse(url).hostname in SITE_HOSTS


def mod_page_url(page: AyakaPage) -> str:
    """Link the page the browser downloads from; e.g. ``mod_page_url(AyakaPage(7322))``."""
    # The site redirects ID-only paths to the slugged page.
    return f"{SITE_ROOT}/mods/{page.mod_id}/"


def _ld_json_blocks(page_html: str) -> tuple[object, ...]:
    blocks: list[object] = []
    for match in LD_JSON_BLOCK.finditer(page_html):
        try:
            block = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue  # A broken unrelated block must not hide the mod's.
        # Mod pages ship one array: the mod, its breadcrumbs, and the page.
        blocks.extend(block if isinstance(block, list) else (block,))
    return tuple(blocks)


def _mod_block(page_html: str) -> dict[str, object]:
    for block in _ld_json_blocks(page_html):
        if (
            isinstance(block, dict)
            and block.get("applicationSubCategory") == MOD_SUBCATEGORY
        ):
            return block
    raise ValueError(
        "AyakaMods page: expected a JSON-LD block with "
        f"applicationSubCategory={MOD_SUBCATEGORY!r}"
    )


def _text(block: dict[str, object], key: str) -> str:
    value = block.get(key)
    return value if isinstance(value, str) else ""


def _author(block: dict[str, object]) -> str:
    author = block.get("author")
    return _text(author, "name") if isinstance(author, dict) else ""


def _picture_url(block: dict[str, object]) -> str | None:
    value = _text(block, "image")
    if not value:
        return None
    absolute = parse.urljoin(SITE_ROOT, value)
    if parse.urlparse(absolute).scheme != "https":
        raise ValueError(f"AyakaMods image={value!r}: expected an HTTPS URL")
    return absolute


def parse_mod_page(page_html: str) -> AyakaModDetails:
    """Read page details; e.g. ``parse_mod_page(html).info.name == 'Sample Retexture'``."""
    block = _mod_block(page_html)
    name = _text(block, "name")
    if not name:
        raise ValueError(f"AyakaMods mod name={block.get('name')!r}: expected text")
    info = NexusModInfo(
        name,
        _text(block, "description"),
        _author(block),
        _text(block, "softwareVersion"),
        _picture_url(block),
    )
    return AyakaModDetails(info, _text(block, "genre"), _text(block, "dateModified"))


def fetch_mod_details(
    transport: AyakaPageTransport, page: AyakaPage
) -> AyakaModDetails:
    """Fetch and read one page; e.g. ``fetch_mod_details(http, AyakaPage(7322))``."""
    return parse_mod_page(transport.get_text(mod_page_url(page)))
