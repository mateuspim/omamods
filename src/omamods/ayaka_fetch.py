"""Download an AyakaMods file straight into staging, as Nexus downloads do.

Each download asks the site first, so the file keeps the name and size the
site gives it, then streams with Nexus' retries, resume, and queue updates.
"""

from dataclasses import replace
from pathlib import Path
from urllib import parse

from omamods.ayaka_download import (
    AyakaHostedElsewhere,
    AyakaLoginRequired,
    AyakaOffer,
    AyakaReply,
    AyakaSession,
)
from omamods.ayaka_pages import SITE_HOSTS
from omamods.ayaka_staging import AYAKA_FILE_CATEGORY
from omamods.cdn_download import RetryPolicy
from omamods.download_queue import DOWNLOADING, DownloadLog
from omamods.mod_fetch import tracked_download
from omamods.mod_sites import AYAKA_SITE
from omamods.nexus_api import NexusFile
from omamods.pak_games import PakOverlayGame
from omamods.pak_storage import archive_path
from omamods.staging import (
    load_mod_details,
    mod_folder,
    save_mod_details,
    staged_archives,
)


def _file_reply(session: AyakaSession, offer: AyakaOffer) -> AyakaReply:
    reply = session.probe(offer.url)
    if parse.urlparse(reply.final_url).hostname not in SITE_HOSTS:
        raise AyakaHostedElsewhere(reply.final_url)
    if reply.page_html:
        raise AyakaLoginRequired(
            f"AyakaMods file={offer.label!r}: expected a file, got a web page; "
            "the login cookie may have expired (:ayaka-login)"
        )
    if reply.file_name is None:
        raise ValueError(
            f"AyakaMods file={offer.label!r}: expected a file name in its "
            "Content-Disposition header"
        )
    return reply


def _file_id(
    folder: Path, files: tuple[NexusFile, ...], offer: AyakaOffer, name: str
) -> int:
    if offer.attachment_id is not None:
        return offer.attachment_id
    # A page's only file has no ID; one with the same name is the same file.
    same = next((f.file_id for f in files if f.file_name == name), None)
    if same is not None:
        return same
    used = {file.file_id for file in files} | set(staged_archives(folder))
    return max(used, default=0) + 1


def _ayaka_file(
    folder: Path, files: tuple[NexusFile, ...], offer: AyakaOffer, reply: AyakaReply
) -> NexusFile:
    name = reply.file_name or offer.label
    size_kb = (reply.size or 0) // 1024
    file_id = _file_id(folder, files, offer, name)
    return NexusFile(file_id, name, AYAKA_FILE_CATEGORY, 0, offer.label, "", size_kb)


def _record_file(folder: Path, file: NexusFile) -> None:
    info, files = load_mod_details(folder)
    if info is None:
        return  # Without page details the file is still listed from disk.
    kept = tuple(item for item in files if item.file_id != file.file_id)
    save_mod_details(folder, info, kept + (file,))


def stage_ayaka_offer(
    session: AyakaSession,
    root: Path,
    game: PakOverlayGame,
    mod_id: int,
    offer: AyakaOffer,
    log: DownloadLog,
    retry: RetryPolicy = RetryPolicy(),
) -> Path:
    """Download one offered file; e.g. ``stage_ayaka_offer(s, root, co, 7311, offer, log)``."""
    reply = _file_reply(session, offer)
    folder = mod_folder(root, game, mod_id)
    file = _ayaka_file(folder, load_mod_details(folder)[1], offer, reply)
    destination = archive_path(root, game, mod_id, file)
    status = log.begin(game.game_id, mod_id, file, DOWNLOADING, AYAKA_SITE)
    path = tracked_download(log, status, destination, offer.url, session, file, retry)
    _record_file(folder, replace(file, uploaded_timestamp=int(path.stat().st_mtime)))
    return path
