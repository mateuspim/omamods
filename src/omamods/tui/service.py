"""Everything the TUI does, behind one injectable object the screens call."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from omamods.adult_marks import AdultMarks, load_adult_marks, save_adult_marks
from omamods.ayaka_download import AyakaSession
from omamods.ayaka_pages import AyakaPage, AyakaPageTransport
from omamods.ayaka_pages import mod_page_url as ayaka_page_url
from omamods.game_shelf import GameShelf, ShelfScanner
from omamods.download_queue import DOWNLOADING, QUEUED, DownloadStatus, shown_state
from omamods.mod_fetch import (
    BrowserDownloadRequired,
    download_log,
    fetch_picture,
    stage_file,
    stage_mod_details,
)
from omamods.nexus_api import (
    NexusApi,
    NexusFile,
    NexusPage,
    NexusTransport,
    describe_nexus_file,
)
from omamods.nexus_api import parse_nexus_page
from omamods.nexus_config import ConfigFiles, UserSettings, load_user_config
from omamods.nexus_config import save_api_key
from omamods.nexus_workflow import (
    LocalArchiveRequest,
    install_local_archive,
    revert_mod_files,
)
from omamods.cdn_download import RetryPolicy
from omamods.browser_hiding import HiddenWindows
from omamods.browser_queue import STAY, BrowserQueue
from omamods.browser_windows import NexusWindows
from omamods.host_programs import CommandRunner, Launcher
from omamods.nxm_handler import (
    NxmRegistration,
    nxm_entry_outdated,
    register_nxm_handler,
)
from omamods.asset_plans import game_variants, plan_game_assets
from omamods.pak_archive import ArchiveReader, PlannedAsset
from omamods.detected_games import load_detected_games, save_detected_games
from omamods.pak_detection import scanned_pak_games
from omamods.pak_games import PakGameCatalog, PakOverlayGame
from omamods.tui.ayaka_site import AyakaSite
from omamods.tui.release_site import ReleaseSite
from omamods.tui.steam_setup import SteamSetup
from omamods.tui.asset_conflicts import AssetConflicts
from omamods.tui.game_uninstall import GameUninstall
from omamods.byte_ranges import FileRanges
from omamods.installed_containers import OpenRanges
from omamods.steam_process import SteamProcess
from omamods.tui.requirement_flow import RequirementFlow
from omamods.variant_choices import exclusive_variants, nested_archives
from omamods.omarchy_palette import OmarchyPalette, PaletteReader
from omamods.mod_sites import AYAKA_SITE, NEXUS_SITE, RELEASE_SITE
from omamods.release_api import ReleaseTransport
from omamods.staging import (
    StagedMod,
    list_staged_mods,
    load_staged_mod,
    mod_folder,
    remove_staged_archive,
)

PaksLocator = Callable[[PakOverlayGame, UserSettings], Path]
# Maps a Steam app ID to every local user's launch options for it.
LaunchOptionsReader = Callable[[str], tuple[str, ...]]
# Writes (app ID, line) into Steam's configs, backing them up into a folder.
LaunchOptionsWriter = Callable[[str, str, Path], tuple[Path, ...]]


def no_launch_options(app_id: str) -> tuple[str, ...]:
    """Stand in when Steam is not searched; e.g. ``no_launch_options('1091500')``."""
    return ()


@dataclass(frozen=True)
class TuiHost:
    """Host paths and I/O adapters the TUI needs."""

    config_path: Path
    fallback_root: Path
    environment: Mapping[str, str]
    config_files: ConfigFiles
    transport: NexusTransport
    reader: ArchiveReader
    runner: CommandRunner
    launcher: Launcher
    locate_paks: PaksLocator
    executable: Path
    applications: Path
    scan_shelf: ShelfScanner
    browser: str | None = None
    retry: RetryPolicy = RetryPolicy()
    read_launch_options: LaunchOptionsReader = no_launch_options
    ayaka_pages: AyakaPageTransport | None = None
    # Opens a logged-in session from the saved xf_user cookie.
    ayaka_session: Callable[[str], AyakaSession] | None = None
    # Where the browser saves files, watched for AyakaMods downloads.
    downloads: Path | None = None
    palette_reader: PaletteReader | None = None
    # Reads Codeberg/GitHub releases anonymously (MGSVFix).
    release_transport: ReleaseTransport | None = None
    write_launch_options: LaunchOptionsWriter | None = None
    steam: SteamProcess | None = None
    # Reads pak and utoc indexes for asset collision checks.
    open_ranges: OpenRanges = FileRanges


class ModsService:
    """Stage, install, and revert mods for the TUI; e.g. ``ModsService(host)``."""

    def __init__(self, host: TuiHost) -> None:
        self.host = host
        self.settings = self._load_settings()
        self.windows = NexusWindows(host.runner, host.launcher, host.browser)
        self.browser_queue = BrowserQueue()
        self.hidden_windows = HiddenWindows()
        # Until the first scan, reuse the last one so queued downloads resolve.
        self.catalog = PakGameCatalog(load_detected_games(self.settings.storage_root))
        self.requirements = RequirementFlow(self)
        self.ayaka = AyakaSite(self)
        self.release = ReleaseSite(self)
        self.steam_setup = SteamSetup(self)
        self.conflicts = AssetConflicts(self)
        self.game_uninstall = GameUninstall(self)

    def _load_settings(self) -> UserSettings:
        host = self.host
        try:
            return load_user_config(
                host.config_path,
                host.fallback_root,
                host.environment.get("NEXUS_API_KEY"),
                host.config_files,
            )
        except ValueError as error:
            if not isinstance(error.__cause__, FileNotFoundError):
                raise
            return UserSettings("", host.fallback_root, {}, ())

    def games(self) -> tuple[PakOverlayGame, ...]:
        """List supported games; for example, ``service.games()``."""
        return self.catalog.all()

    def theme_palette(self) -> OmarchyPalette | None:
        """Read injected desktop colours; e.g. ``service.theme_palette()``."""
        reader = self.host.palette_reader
        return reader.read() if reader is not None else None

    def shelf(self) -> GameShelf:
        """Find catalog and installed games; e.g. ``service.shelf().entries``."""
        shelf = self.host.scan_shelf(self.settings)
        scanned = scanned_pak_games(shelf)
        self.catalog = PakGameCatalog(scanned)
        # The nxm handler runs in its own process and reads this file.
        save_detected_games(self.settings.storage_root, scanned)
        return shelf

    def has_api_key(self) -> bool:
        """Report whether Nexus calls can work; e.g. ``service.has_api_key()``."""
        return bool(self.settings.api_key)

    def save_api_key(self, api_key: str) -> None:
        """Store and use a key; for example, ``service.save_api_key('abc')``."""
        host = self.host
        save_api_key(
            host.config_path, host.fallback_root, api_key.strip(), host.config_files
        )
        self.settings = self._load_settings()

    def adult_marks(self) -> AdultMarks:
        """Read the NSFW toggle and hand marks; e.g. ``service.adult_marks().mode``."""
        return load_adult_marks(self.settings.storage_root)

    def save_adult_marks(self, marks: AdultMarks) -> Path:
        """Persist NSFW choices; e.g. ``service.save_adult_marks(marks)``."""
        return save_adult_marks(self.settings.storage_root, marks)

    def staging_folder(self, game: PakOverlayGame) -> Path:
        """Show where archives land; e.g. ``service.staging_folder(sb)``."""
        return self.settings.storage_root / "archives" / game.game_id

    def staged_mods(self, game: PakOverlayGame) -> tuple[StagedMod, ...]:
        """List every site's staging; for example, ``service.staged_mods(sb)``."""
        nexus = list_staged_mods(self.settings.storage_root, game)
        return self.release.staged_mods(game) + nexus + self.ayaka.staged_mods(game)

    def staged_mod(
        self, game: PakOverlayGame, mod_id: int, site: str = NEXUS_SITE
    ) -> StagedMod:
        """Reload one mod; for example, ``service.staged_mod(sb, 1)``."""
        if site == AYAKA_SITE:
            return self.ayaka.staged_mod(game, mod_id)
        if site == RELEASE_SITE:
            return self.release.staged_mod(game, mod_id)
        return load_staged_mod(self.settings.storage_root, game, mod_id)

    def state_root(self, site: str) -> Path:
        """Where a site's archives and records live; e.g. ``state_root('ayaka')``."""
        return self._root(site)

    def _root(self, site: str) -> Path:
        if site == RELEASE_SITE:
            return self.release.root()
        return self.ayaka.root() if site == AYAKA_SITE else self.settings.storage_root

    def nexus_api(self) -> NexusApi:
        """Call Nexus with the saved key; for example, ``service.nexus_api().files(p)``."""
        if not self.settings.api_key:
            raise ValueError("Nexus API key: expected one; press K to add it")
        return NexusApi(self.host.transport, self.settings.api_key)

    def fetch_mod(self, game: PakOverlayGame, url: str) -> StagedMod:
        """Stage page details; e.g. ``service.fetch_mod(sb, 'https://...')``."""
        page = parse_nexus_page(url.strip())
        return stage_mod_details(
            self.nexus_api(), game, page, self.settings.storage_root
        )

    def download(self, game: PakOverlayGame, mod_id: int, file: NexusFile) -> Path:
        """Stage one archive; e.g. ``service.download(sb, 1, file)``."""
        page = NexusPage(game.nexus_domain, mod_id)
        root = self.settings.storage_root
        return stage_file(
            self.nexus_api(), game, page, file, root, None, self.host.retry
        )

    def fetch_file(self, game: PakOverlayGame, mod_id: int, file: NexusFile) -> bool:
        """Download, or hand off to the site; True when staged. E.g. ``fetch_file(sb, 1, f)``."""
        try:
            self.download(game, mod_id, file)
        except BrowserDownloadRequired as required:
            self._await_browser(game, mod_id, file.file_id, required.url)
            return False
        return True

    def _await_browser(
        self, game: PakOverlayGame, mod_id: int, file_id: int, url: str
    ) -> None:
        staged = self.staged_mod(game, mod_id).archives.keys()
        if self.browser_queue.add(game.game_id, mod_id, file_id, url, staged):
            self.open_nexus(url)

    def advance_browser_downloads(self) -> tuple[str, ...]:
        """Move Nexus windows on as files arrive; e.g. ``service.advance_browser_downloads()``."""
        messages: list[str] = []
        for game_id, mod_id in list(self.browser_queue.pending):
            game = self.catalog.get(game_id)
            mod = self.staged_mod(game, mod_id)
            step = self.browser_queue.advance(game_id, mod_id, mod.archives.keys())
            messages.extend(self._surprise_messages(game_id, mod, step.unexpected))
            if step.action == STAY:
                continue
            self.close_nexus_window(game, mod_id)
            self.hidden_windows.forget((game_id, mod_id))
            if step.url is None:
                messages.append(f"{mod.title}: all files downloaded; closed Nexus")
                continue
            self.open_nexus(step.url)
            messages.append(f"{mod.title}: file arrived; opening the next one")
        return tuple(messages) + self._move_browser_windows()

    def _move_browser_windows(self) -> tuple[str, ...]:
        waiting = self.browser_queue.waiting_files()
        if not waiting:
            return ()
        statuses = self.downloads()
        for game_id, mod_id in self.hidden_windows.to_hide(waiting, statuses):
            self.windows.hide_mod(self.catalog.get(game_id).nexus_domain, mod_id)
        restored = self.hidden_windows.to_restore(waiting, statuses)
        return tuple(
            self._reopen_popup(game_id, mod_id) for game_id, mod_id in restored
        )

    def _reopen_popup(self, game_id: str, mod_id: int) -> str:
        game = self.catalog.get(game_id)
        self.close_nexus_window(game, mod_id)
        url = self.browser_queue.waiting_url(game_id, mod_id)
        if url is not None:
            self.open_nexus(url)
        title = self.staged_mod(game, mod_id).title
        return f"{title}: download failed; reopened Nexus so you can click again"

    def _surprise_messages(
        self, game_id: str, mod: StagedMod, unexpected: tuple[int, ...]
    ) -> list[str]:
        names = {f.file_id: describe_nexus_file(f) for f in mod.files}
        waiting = self.browser_queue.waiting_for(game_id, mod.mod_id)
        still = f"; still waiting for {names.get(waiting, waiting)}" if waiting else ""
        return [
            f"{mod.title}: Nexus sent {names.get(file_id, file_id)}, which you did not "
            f"ask for{still}. Select it and press x to remove it."
            for file_id in unexpected
        ]

    def mark_queued(
        self, game: PakOverlayGame, mod_id: int, files: tuple[NexusFile, ...]
    ) -> None:
        """Show files as queued before they start; e.g. ``mark_queued(sb, 1, files)``."""
        log = download_log(self.settings.storage_root)
        staged = self.staged_mod(game, mod_id).archives
        for file in files:
            if file.file_id not in staged:
                log.begin(game.game_id, mod_id, file, QUEUED)

    def downloads(self) -> tuple[DownloadStatus, ...]:
        """Read the shared queue, newest first; e.g. ``service.downloads()``."""
        return download_log(self.settings.storage_root).statuses()

    def clear_finished_downloads(self) -> int:
        """Drop done and failed entries; e.g. ``service.clear_finished_downloads()``."""
        return download_log(self.settings.storage_root).clear_finished()

    def remove_download(self, status: DownloadStatus) -> None:
        """Drop one entry and its Nexus popup; e.g. ``service.remove_download(s)``."""
        log = download_log(self.settings.storage_root)
        if shown_state(status, log.clock()) == DOWNLOADING:
            raise ValueError(
                f"download={status.file_name!r} is still receiving data; "
                "expected a queued, waiting, stalled, done, or failed entry"
            )
        log.remove(status)
        # Ayaka numbers mods on its own, so its IDs could match a Nexus popup's.
        if status.site == NEXUS_SITE:
            self._forget_browser_file(status.game_id, status.mod_id, status.file_id)

    def clear_download_queue(self) -> int:
        """Drop all but moving downloads; e.g. ``service.clear_download_queue()``."""
        count = download_log(self.settings.storage_root).clear_idle()
        live = {
            (s.game_id, s.mod_id, s.file_id)
            for s in self.downloads()
            if s.site == NEXUS_SITE
        }
        for (game_id, mod_id), queue in list(self.browser_queue.pending.items()):
            for file_id, _ in list(queue):
                if (game_id, mod_id, file_id) not in live:
                    self._forget_browser_file(game_id, mod_id, file_id)
        return count

    def _forget_browser_file(self, game_id: str, mod_id: int, file_id: int) -> None:
        step = self.browser_queue.drop(game_id, mod_id, file_id)
        if step.action == STAY:
            return
        self.close_nexus_window(self.catalog.get(game_id), mod_id)
        self.hidden_windows.forget((game_id, mod_id))
        if step.url is not None:
            self.open_nexus(step.url)

    def retry(self, status: DownloadStatus) -> bool:
        """Fetch a queue entry again; True when staged. E.g. ``service.retry(s)``."""
        game = self.catalog.get(status.game_id)
        if status.site == AYAKA_SITE:
            self.ayaka.retry(game, status.mod_id, status.file_id)
            return True
        if status.site == RELEASE_SITE:
            self.release.retry(game, status.mod_id, status.file_id)
            return True
        mod = self.staged_mod(game, status.mod_id)
        file = next((f for f in mod.files if f.file_id == status.file_id), None)
        if file is None:
            raise ValueError(
                f"file_id={status.file_id}: expected it in mod {status.mod_id}'s details"
            )
        return self.fetch_file(game, status.mod_id, file)

    def mod_page_url(
        self, game: PakOverlayGame, mod_id: int, site: str = NEXUS_SITE
    ) -> str:
        """Link a mod page; for example, ``service.mod_page_url(sb, 1)``."""
        if site == AYAKA_SITE:
            return ayaka_page_url(AyakaPage(mod_id))
        if site == RELEASE_SITE:
            return self.release.page_url(game, mod_id)
        return f"https://www.nexusmods.com/{game.nexus_domain}/mods/{mod_id}"

    def open_url(self, url: str) -> None:
        """Open the browser; for example, ``service.open_url(url)``."""
        self.host.launcher.launch(("xdg-open", url))

    def copy_to_clipboard(self, text: str) -> None:
        """Put text on the Wayland clipboard; e.g. ``service.copy_to_clipboard(line)``."""
        # Detached: wl-copy stays running to serve the paste, so waiting hangs.
        self.host.launcher.launch(("wl-copy", "--", text))

    def open_folder(self, folder: Path) -> None:
        """Show a game folder in the file manager; e.g. ``service.open_folder(p)``."""
        self.host.launcher.launch(("xdg-open", str(folder)))

    def open_nexus(self, url: str) -> bool:
        """Open a closable Nexus window; e.g. ``service.open_nexus(url)``."""
        return self.windows.open(url)

    def close_nexus_window(self, game: PakOverlayGame, mod_id: int) -> int:
        """Close a mod's Nexus window; e.g. ``service.close_nexus_window(sb, 1)``."""
        return self.windows.close_mod(game.nexus_domain, mod_id)

    def open_picture(self, picture: Path) -> None:
        """Show the full image in imv; e.g. ``service.open_picture(path)``."""
        self.host.launcher.launch(("imv", str(picture)))

    def variants(self, game: PakOverlayGame, archive: Path) -> tuple[str, ...]:
        """List variant folders; e.g. ``service.variants(sb, archive)``."""
        return game_variants(self.host.reader.members(archive), game)

    def exclusive_variants(
        self, archive: Path, variants: tuple[str, ...]
    ) -> Mapping[str, frozenset[str]]:
        """Pair alternatives; e.g. ``service.exclusive_variants(archive, ('A', 'B'))``."""
        return exclusive_variants(self.host.reader.members(archive), variants)

    def nested_archives(self, archive: Path) -> tuple[str, ...]:
        """List archives an install skips; e.g. ``service.nested_archives(archive)``."""
        return nested_archives(self.host.reader.members(archive))

    def plan(
        self, game: PakOverlayGame, archive: Path, option: str | None
    ) -> tuple[PlannedAsset, ...]:
        """Preview targets; e.g. ``service.plan(sb, archive, 'Black')``."""
        return plan_game_assets(self.host.reader.members(archive), game, option)

    def install(
        self,
        game: PakOverlayGame,
        mod_id: int,
        file_id: int,
        option: str | None,
        site: str = NEXUS_SITE,
    ) -> int:
        """Install a staged file; e.g. ``service.install(sb, 1, 7, None)``."""
        archive = self.staged_mod(game, mod_id, site).archives[file_id]
        paks = self.host.locate_paks(game, self.settings)
        request = LocalArchiveRequest(archive, mod_id, file_id, option)
        # Records go beside the site's staging, so Ayaka IDs never meet Nexus'.
        settings = replace(self.settings, storage_root=self._root(site))
        installed = install_local_archive(
            game, settings, paks, request, self.host.reader
        )
        return installed[1]

    def fetch_missing_picture(self, game: PakOverlayGame, mod: StagedMod) -> Path:
        """Download a mod's picture if Nexus lists one; e.g. ``service.fetch_missing_picture(sb, mod)``."""
        if mod.info is None:
            # Staging page details also saves the picture.
            url = self.mod_page_url(game, mod.mod_id, mod.site)
            add = self.ayaka.add if mod.site == AYAKA_SITE else self.fetch_mod
            mod = add(game, url)
        if mod.picture is not None:
            return mod.picture
        if mod.info is None or mod.info.picture_url is None:
            raise ValueError(
                f"{mod.title}: expected a picture URL in its Nexus details"
            )
        folder = mod_folder(self._root(mod.site), game, mod.mod_id)
        return fetch_picture(self.host.transport, folder, mod.info.picture_url)

    def remove_staged(
        self, game: PakOverlayGame, mod_id: int, file_id: int, site: str = NEXUS_SITE
    ) -> Path:
        """Delete a downloaded file; e.g. ``service.remove_staged(sb, 365, 1028)``."""
        return remove_staged_archive(self._root(site), game, mod_id, file_id)

    def revert(
        self, game: PakOverlayGame, mod_id: int, file_id: int, site: str = NEXUS_SITE
    ) -> int:
        """Remove one installed file; e.g. ``service.revert(sb, 1, 7)``."""
        return revert_mod_files(game, self._root(site), mod_id, file_id)

    def register_nxm(self) -> NxmRegistration:
        """Receive site download clicks; e.g. ``service.register_nxm()``."""
        host = self.host
        return register_nxm_handler(host.executable, host.applications, host.runner)

    def refresh_outdated_nxm(self) -> NxmRegistration | None:
        """Re-point an old handler here; e.g. ``service.refresh_outdated_nxm()``."""
        if not nxm_entry_outdated(self.host.executable, self.host.applications):
            return None
        return self.register_nxm()
