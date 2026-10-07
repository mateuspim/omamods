"""Fetch a mod's page details, main picture, and archives into staging."""

from dataclasses import dataclass, replace
from pathlib import Path

from omamods.cdn_download import NexusHttpError, RetryPolicy
from omamods.download_queue import (
    DOWNLOADING,
    WAITING_FOR_BROWSER,
    DownloadLog,
    DownloadStatus,
    ProgressRecorder,
)
from omamods.nexus_api import (
    NexusApi,
    NexusFile,
    NexusModInfo,
    NexusPage,
    NexusTransport,
    NxmAuthorization,
    describe_nexus_file,
    select_file,
)
from omamods.pak_games import PAK_OVERLAY_GAMES, PakOverlayGame
from omamods.pak_storage import PARTIAL_SUFFIX, archive_path, download_archive
from omamods.staging import (
    StagedMod,
    load_staged_mod,
    mod_folder,
    picture_path,
    save_mod_details,
)


class BrowserDownloadRequired(ValueError):
    """Nexus allows API downloads only for Premium; others click on the site."""

    def __init__(self, url: str) -> None:
        super().__init__(
            f"Nexus download: expected a Premium key for API downloads; open {url} "
            "and click 'Mod Manager Download'"
        )
        self.url = url


def files_tab_url(page: NexusPage, file_id: int) -> str:
    """Link the site's download button; e.g. ``files_tab_url(page, 7)``."""
    return (
        f"https://www.nexusmods.com/{page.domain}/mods/{page.mod_id}"
        f"?tab=files&file_id={file_id}&nmm=1"
    )


def game_for_domain(domain: str) -> PakOverlayGame:
    """Map a Nexus domain to a game; e.g. ``game_for_domain('stellarblade')``."""
    for game in PAK_OVERLAY_GAMES.values():
        if game.nexus_domain == domain:
            return game
    supported = sorted(game.nexus_domain for game in PAK_OVERLAY_GAMES.values())
    raise ValueError(f"Nexus domain={domain!r}: expected one of {supported!r}")


def fetch_picture(transport: NexusTransport, folder: Path, url: str) -> Path:
    """Download the main picture, raising on failure; e.g. ``fetch_picture(http, folder, url)``."""
    existing = sorted(folder.glob("picture.*"))
    if existing:
        return existing[0]
    target = picture_path(folder, url)
    folder.mkdir(parents=True, exist_ok=True)
    partial = folder / f".picture{PARTIAL_SUFFIX}"
    try:
        with partial.open("wb") as stream:
            transport.download(url, stream)
        target = target.with_suffix(sniffed_suffix(partial) or target.suffix)
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return target


def sniffed_suffix(image: Path) -> str | None:
    """Name an image by its bytes; e.g. ``sniffed_suffix(Path('a')) == '.webp'``."""
    # Nexus' CDN serves WebP even for '.png'/'.jpeg' URLs.
    with image.open("rb") as stream:
        head = stream.read(12)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head.startswith(b"\x89PNG"):
        return ".png"
    if head.startswith(b"\xff\xd8"):
        return ".jpg"
    return None


def stage_picture(transport: NexusTransport, folder: Path, info: NexusModInfo) -> bool:
    """Cache the main picture if possible; e.g. ``stage_picture(http, folder, info)``."""
    if info.picture_url is None:
        return False
    try:
        fetch_picture(transport, folder, info.picture_url)
    except (OSError, ValueError):
        # A missing picture must not block staging the mod; the TUI retries it.
        return False
    return True


def stage_mod_details(
    api: NexusApi, game: PakOverlayGame, page: NexusPage, root: Path
) -> StagedMod:
    """Fetch page details and picture; e.g. ``stage_mod_details(api, sb, page, root)``."""
    if page.domain != game.nexus_domain:
        raise ValueError(
            f"Nexus domain={page.domain!r}: expected {game.nexus_domain!r}"
        )
    info, files = api.mod_info(page), api.files(page)
    folder = mod_folder(root, game, page.mod_id)
    save_mod_details(folder, info, files)
    stage_picture(api.transport, folder, info)
    return load_staged_mod(root, game, page.mod_id)


def stage_file(
    api: NexusApi,
    game: PakOverlayGame,
    page: NexusPage,
    file: NexusFile,
    root: Path,
    nxm: NxmAuthorization | None,
    retry: RetryPolicy = RetryPolicy(),
) -> Path:
    """Download one archive into staging; e.g. ``stage_file(api, sb, page, f, root, None)``."""
    destination = archive_path(root, game, page.mod_id, file)
    if destination.is_file():
        return destination
    log = download_log(root)
    status = log.begin(game.game_id, page.mod_id, file, DOWNLOADING)
    try:
        uri = _download_uri(api, page, file, nxm)
    except BrowserDownloadRequired:
        log.update(replace(status, state=WAITING_FOR_BROWSER))
        raise
    except BaseException as error:
        log.finish(status, _reason(error))
        raise
    return _tracked_download(log, status, destination, uri, api.transport, file, retry)


def download_log(root: Path) -> DownloadLog:
    """Open the shared queue; for example, ``download_log(storage_root)``."""
    return DownloadLog(root / "downloads")


def _reason(error: BaseException) -> str:
    return str(error) or type(error).__name__


def _download_uri(
    api: NexusApi, page: NexusPage, file: NexusFile, nxm: NxmAuthorization | None
) -> str:
    try:
        return api.download_url(page, file, nxm)
    except NexusHttpError as error:
        if error.code != 403 or nxm is not None:
            raise
        raise BrowserDownloadRequired(files_tab_url(page, file.file_id)) from error


def _tracked_download(
    log: DownloadLog,
    status: DownloadStatus,
    destination: Path,
    uri: str,
    transport: NexusTransport,
    file: NexusFile,
    retry: RetryPolicy,
) -> Path:
    recorder = ProgressRecorder(log, status)
    try:
        noting = replace(retry, on_retry=recorder.note_retry)
        path = download_archive(destination, file, uri, transport, recorder, noting)
    except BaseException as error:
        log.finish(recorder.status, _reason(error))
        raise
    log.finish(recorder.status, None)
    return path


@dataclass(frozen=True)
class ClickedDownload:
    """The file a site click actually named, which may not be the one requested."""

    game: PakOverlayGame
    file: NexusFile
    archive: Path

    def describe(self) -> str:
        """Name it for people; for example, ``clicked.describe()``."""
        return describe_nexus_file(self.file)


def stage_nxm_link(
    api: NexusApi, root: Path, link: NxmAuthorization
) -> ClickedDownload:
    """Handle a site download click; e.g. ``stage_nxm_link(api, root, link)``."""
    game = game_for_domain(link.domain)
    page = NexusPage(link.domain, link.mod_id)
    staged = stage_mod_details(api, game, page, root)
    file = select_file(staged.files, link.file_id)
    return ClickedDownload(game, file, stage_file(api, game, page, file, root, link))
