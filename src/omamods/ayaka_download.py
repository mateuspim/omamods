"""Download AyakaMods files as the logged-in user, with their login cookie.

The site serves files only to a logged-in session and its API is not public,
so OmaMods sends the user's ``xf_user`` cookie (XenForo's "stay logged in"
cookie) to ayakamods.com, and never to another host a download redirects to.
"""

from dataclasses import dataclass
from email.message import Message
from http.client import HTTPException, HTTPResponse
import html
import re
from typing import BinaryIO, Protocol
from urllib import error, parse, request

from omamods.ayaka_pages import SITE_HOSTS, SITE_ROOT, AyakaPage
from omamods.cdn_download import (
    USER_AGENT,
    NexusHttpError,
    ProgressCallback,
    TransientDownloadError,
    copy_response,
)

LOGGED_OUT_MARKER = 'data-logged-in="false"'
CHOICE_LINK = re.compile(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
TAG = re.compile(r"<[^>]+>")


class AyakaHttpError(NexusHttpError):
    """An AyakaMods HTTP failure; retries treat 5xx/429 like Nexus' (``is_transient``)."""

    def __init__(self, code: int, expected: str) -> None:
        ValueError.__init__(self, f"AyakaMods HTTP {code}: expected {expected}")
        self.code = code


class AyakaLoginRequired(ValueError):
    """The cookie is missing or expired; the browser flow still works."""


class AyakaHostedElsewhere(ValueError):
    """The mod's download lives on another site, e.g. a Mega or Drive link."""

    def __init__(self, url: str) -> None:
        super().__init__(
            f"AyakaMods download={url!r}: expected a file on ayakamods.com; "
            "it is hosted elsewhere, so download it in the browser"
        )
        self.url = url


@dataclass(frozen=True)
class AyakaReply:
    """What a download URL answered: a file's name and size, or an HTML page."""

    final_url: str
    file_name: str | None
    size: int | None
    page_html: str


@dataclass(frozen=True)
class AyakaOffer:
    """One file a mod offers; ``attachment_id`` is None for a page's only file."""

    url: str
    label: str
    attachment_id: int | None


class AyakaSession(Protocol):
    """Logged-in HTTP; tests inject a named fake."""

    def probe(self, url: str) -> AyakaReply:
        """Read headers, or the page if HTML; e.g. ``session.probe(url)``."""
        ...

    def download(
        self,
        url: str,
        destination: BinaryIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Stream a file from an offset; e.g. ``session.download(url, f)``."""
        ...


def download_url(page: AyakaPage) -> str:
    """Link a mod's download button; e.g. ``download_url(AyakaPage(7311))``."""
    return f"{SITE_ROOT}/mods/{page.mod_id}/download"


def attachment_name(disposition: str | None) -> str | None:
    """Read a safe file name; e.g. ``attachment_name('attachment; filename="a.zip"')``."""
    if not disposition:
        return None
    header = Message()
    header["content-disposition"] = disposition
    name = header.get_filename()
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return None
    return name


def _choice(href: str, text: str, mod_id: int) -> AyakaOffer | None:
    url = parse.urljoin(SITE_ROOT, html.unescape(href))
    parsed = parse.urlparse(url)
    on_mod = re.fullmatch(rf"/mods/(?:[^/]*\.)?{mod_id}/download", parsed.path)
    file_ids = parse.parse_qs(parsed.query).get("file", [])
    if parsed.hostname not in SITE_HOSTS or not on_mod or len(file_ids) != 1:
        return None
    if not file_ids[0].isdecimal():
        return None
    label = " ".join(html.unescape(TAG.sub(" ", text)).split())
    return AyakaOffer(url, label or f"file {file_ids[0]}", int(file_ids[0]))


def parse_file_choices(page_html: str, mod_id: int) -> tuple[AyakaOffer, ...]:
    """List a multi-file mod's download links; e.g. ``parse_file_choices(html, 7311)``."""
    offers: dict[int, AyakaOffer] = {}
    for href, text in CHOICE_LINK.findall(page_html):
        offer = _choice(href, text, mod_id)
        if offer is not None and offer.attachment_id is not None:
            offers.setdefault(offer.attachment_id, offer)
    return tuple(offers.values())


def _offers_from_page(reply: AyakaReply, page: AyakaPage) -> tuple[AyakaOffer, ...]:
    if LOGGED_OUT_MARKER in reply.page_html:
        raise AyakaLoginRequired(
            "AyakaMods login cookie: expected a logged-in session; it is missing "
            "or expired, so copy xf_user from the browser again (:ayaka-login)"
        )
    offers = parse_file_choices(reply.page_html, page.mod_id)
    if not offers:
        raise ValueError(
            f"AyakaMods mod {page.mod_id} download page={reply.final_url!r}: "
            "expected a file or links to its files"
        )
    return offers


def list_offers(session: AyakaSession, page: AyakaPage) -> tuple[AyakaOffer, ...]:
    """Find what a mod offers; e.g. ``list_offers(session, AyakaPage(7311))``."""
    url = download_url(page)
    reply = session.probe(url)
    if parse.urlparse(reply.final_url).hostname not in SITE_HOSTS:
        raise AyakaHostedElsewhere(reply.final_url)
    if reply.page_html:
        return _offers_from_page(reply, page)
    return (AyakaOffer(url, reply.file_name or f"mod-{page.mod_id}", None),)


class SameSiteCookieRedirects(request.HTTPRedirectHandler):
    """Follow redirects, dropping the login cookie when one leaves ayakamods.com."""

    def redirect_request(
        self,
        req: request.Request,
        fp: BinaryIO,
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> request.Request | None:
        """Copy the request for ``newurl``; urllib calls this on 30x replies."""
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and parse.urlparse(newurl).hostname not in SITE_HOSTS:
            new.remove_header("Cookie")
        return new


class UrlAyakaSession:
    """Send the login cookie over HTTPS; e.g. ``UrlAyakaSession('123,abc')``."""

    def __init__(self, login_cookie: str) -> None:
        self.login_cookie = login_cookie
        self.opener = request.build_opener(SameSiteCookieRedirects())

    def _request(self, url: str, resume_from: int = 0) -> request.Request:
        headers = {"User-Agent": USER_AGENT, "Cookie": f"xf_user={self.login_cookie}"}
        if resume_from:
            headers["Range"] = f"bytes={resume_from}-"
        return request.Request(url, headers=headers)

    def _open(self, url: str, resume_from: int = 0) -> HTTPResponse:
        try:
            return self.opener.open(self._request(url, resume_from), timeout=60)
        except error.HTTPError as failure:
            raise AyakaHttpError(failure.code, "a file or download page") from failure
        except (
            error.URLError,
            HTTPException,
            ConnectionError,
            TimeoutError,
        ) as failure:
            reason = getattr(failure, "reason", failure)
            raise TransientDownloadError(f"AyakaMods: {reason}") from failure

    def probe(self, url: str) -> AyakaReply:
        """Read headers, or the page if HTML; e.g. ``session.probe(url)``."""
        with self._open(url) as reply:
            final = reply.geturl()
            if reply.headers.get_content_type() == "text/html":
                text = reply.read().decode("utf-8", errors="replace")
                return AyakaReply(final, None, None, text)
            name = attachment_name(reply.headers.get("Content-Disposition"))
            length = reply.headers.get("Content-Length")
            size = int(length) if length and length.isdecimal() else None
            return AyakaReply(final, name, size, "")

    def download(
        self,
        url: str,
        destination: BinaryIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Stream a file from an offset; e.g. ``session.download(url, f)``."""
        with self._open(url, resume_from) as reply:
            if reply.headers.get_content_type() == "text/html":
                raise AyakaLoginRequired(
                    f"AyakaMods download={url!r}: expected a file, got a web page; "
                    "the login cookie may have expired (:ayaka-login)"
                )
            length = reply.headers.get("Content-Length")
            try:
                copy_response(
                    reply, reply.status, length, destination, progress, resume_from
                )
            except (HTTPException, ConnectionError, TimeoutError) as failure:
                raise TransientDownloadError(f"AyakaMods: {failure}") from failure
