"""Everything the TUI does, behind one injectable object the screens call."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from omamods.download_queue import QUEUED, DownloadStatus
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
from omamods.browser_queue import STAY, BrowserQueue
from omamods.browser_windows import NexusWindows
from omamods.host_programs import CommandRunner, Launcher
from omamods.nxm_handler import NxmRegistration, register_nxm_handler
from omamods.pak_archive import (
    ArchiveReader,
    PlannedAsset,
    plan_pak_assets,
    variant_folders,
)
from omamods.pak_games import PAK_OVERLAY_GAMES, PakOverlayGame, pak_overlay_game
from omamods.staging import (
    StagedMod,
    list_staged_mods,
    load_staged_mod,
    mod_folder,
    remove_staged_archive,
)

PaksLocator = Callable[[PakOverlayGame, UserSettings], Path]


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
    browser: str | None = None
    retry: RetryPolicy = RetryPolicy()


class ModsService:
    """Stage, install, and revert mods for the TUI; e.g. ``ModsService(host)``."""

    def __init__(self, host: TuiHost) -> None:
        self.host = host
        self.settings = self._load_settings()
        self.windows = NexusWindows(host.runner, host.launcher, host.browser)
        self.browser_queue = BrowserQueue()

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
        return tuple(PAK_OVERLAY_GAMES.values())

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

    def staging_folder(self, game: PakOverlayGame) -> Path:
        """Show where archives land; e.g. ``service.staging_folder(sb)``."""
        return self.settings.storage_root / "archives" / game.game_id

    def staged_mods(self, game: PakOverlayGame) -> tuple[StagedMod, ...]:
        """List the staging folder; for example, ``service.staged_mods(sb)``."""
        return list_staged_mods(self.settings.storage_root, game)

    def staged_mod(self, game: PakOverlayGame, mod_id: int) -> StagedMod:
        """Reload one mod; for example, ``service.staged_mod(sb, 1)``."""
        return load_staged_mod(self.settings.storage_root, game, mod_id)

    def _api(self) -> NexusApi:
        if not self.settings.api_key:
            raise ValueError("Nexus API key: expected one; press k to add it")
        return NexusApi(self.host.transport, self.settings.api_key)

    def fetch_mod(self, game: PakOverlayGame, url: str) -> StagedMod:
        """Stage page details; e.g. ``service.fetch_mod(sb, 'https://...')``."""
        page = parse_nexus_page(url.strip())
        return stage_mod_details(self._api(), game, page, self.settings.storage_root)

    def download(self, game: PakOverlayGame, mod_id: int, file: NexusFile) -> Path:
        """Stage one archive; e.g. ``service.download(sb, 1, file)``."""
        page = NexusPage(game.nexus_domain, mod_id)
        root = self.settings.storage_root
        return stage_file(self._api(), game, page, file, root, None, self.host.retry)

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
            game = pak_overlay_game(game_id)
            mod = self.staged_mod(game, mod_id)
            step = self.browser_queue.advance(game_id, mod_id, mod.archives.keys())
            messages.extend(self._surprise_messages(game_id, mod, step.unexpected))
            if step.action == STAY:
                continue
            self.close_nexus_window(game, mod_id)
            if step.url is None:
                messages.append(f"{mod.title}: all files downloaded; closed Nexus")
                continue
            self.open_nexus(step.url)
            messages.append(f"{mod.title}: file arrived; opening the next one")
        return tuple(messages)

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

    def retry(self, status: DownloadStatus) -> bool:
        """Fetch a queue entry again; True when staged. E.g. ``service.retry(s)``."""
        game = pak_overlay_game(status.game_id)
        mod = self.staged_mod(game, status.mod_id)
        file = next((f for f in mod.files if f.file_id == status.file_id), None)
        if file is None:
            raise ValueError(
                f"file_id={status.file_id}: expected it in mod {status.mod_id}'s details"
            )
        return self.fetch_file(game, status.mod_id, file)

    def mod_page_url(self, game: PakOverlayGame, mod_id: int) -> str:
        """Link a mod page; for example, ``service.mod_page_url(sb, 1)``."""
        return f"https://www.nexusmods.com/{game.nexus_domain}/mods/{mod_id}"

    def open_url(self, url: str) -> None:
        """Open the browser; for example, ``service.open_url(url)``."""
        self.host.launcher.launch(("xdg-open", url))

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
        return variant_folders(self.host.reader.members(archive), game)

    def plan(
        self, game: PakOverlayGame, archive: Path, option: str | None
    ) -> tuple[PlannedAsset, ...]:
        """Preview targets; e.g. ``service.plan(sb, archive, 'Black')``."""
        return plan_pak_assets(self.host.reader.members(archive), game, option)

    def install(
        self, game: PakOverlayGame, mod_id: int, file_id: int, option: str | None
    ) -> int:
        """Install a staged file; e.g. ``service.install(sb, 1, 7, None)``."""
        archive = self.staged_mod(game, mod_id).archives[file_id]
        paks = self.host.locate_paks(game, self.settings)
        request = LocalArchiveRequest(archive, mod_id, file_id, option)
        installed = install_local_archive(
            game, self.settings, paks, request, self.host.reader
        )
        return installed[1]

    def fetch_missing_picture(self, game: PakOverlayGame, mod: StagedMod) -> Path:
        """Download a mod's picture if Nexus lists one; e.g. ``service.fetch_missing_picture(sb, mod)``."""
        if mod.info is None or mod.info.picture_url is None:
            raise ValueError(
                f"{mod.title}: expected a picture URL in its Nexus details"
            )
        folder = mod_folder(self.settings.storage_root, game, mod.mod_id)
        return fetch_picture(self.host.transport, folder, mod.info.picture_url)

    def remove_staged(self, game: PakOverlayGame, mod_id: int, file_id: int) -> Path:
        """Delete a downloaded file; e.g. ``service.remove_staged(sb, 365, 1028)``."""
        return remove_staged_archive(self.settings.storage_root, game, mod_id, file_id)

    def revert(self, game: PakOverlayGame, mod_id: int, file_id: int) -> int:
        """Remove one installed file; e.g. ``service.revert(sb, 1, 7)``."""
        return revert_mod_files(game, self.settings.storage_root, mod_id, file_id)

    def register_nxm(self) -> NxmRegistration:
        """Receive site download clicks; e.g. ``service.register_nxm()``."""
        host = self.host
        return register_nxm_handler(host.executable, host.applications, host.runner)
