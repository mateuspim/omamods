"""Everything the TUI does, behind one injectable object the screens call."""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from omamods.adult_marks import AdultMarks, load_adult_marks, save_adult_marks
from omamods.ayaka_pages import AyakaPage
from omamods.ayaka_pages import mod_page_url as ayaka_page_url
from omamods.download_queue import DownloadStatus
from omamods.game_shelf import GameShelf
from omamods.mod_fetch import (
    BrowserDownloadRequired,
    fetch_picture,
    stage_file,
    stage_mod_details,
)
from omamods.nexus_api import NexusApi, NexusFile, NexusPage
from omamods.nexus_api import parse_nexus_page
from omamods.nexus_config import UserSettings, load_user_config
from omamods.nexus_config import save_api_key
from omamods.nexus_workflow import (
    LocalArchiveRequest,
    install_local_archive,
    revert_mod_files,
)
from omamods.browser_windows import NexusWindows
from omamods.nxm_handler import (
    NxmRegistration,
    nxm_entry_missing,
    nxm_entry_outdated,
    register_nxm_handler,
)
from omamods.asset_plans import game_variants, plan_game_assets
from omamods.pak_archive import PlannedAsset
from omamods.detected_games import load_detected_games, save_detected_games
from omamods.pak_detection import scanned_pak_games
from omamods.pak_games import PakGameCatalog, PakOverlayGame
from omamods.tui.ayaka_site import AyakaSite
from omamods.tui.browser_downloads import BrowserDownloads
from omamods.tui.host import TuiHost
from omamods.tui.library_clean import LibraryClean
from omamods.tui.exe_patch_site import ExePatchSite
from omamods.tui.release_site import ReleaseSite
from omamods.tui.steam_setup import SteamSetup
from omamods.tui.asset_conflicts import AssetConflicts
from omamods.tui.game_uninstall import GameUninstall
from omamods.tui.load_order_choices import LoadOrderChoices
from omamods.tui.requirement_flow import RequirementFlow
from omamods.variant_choices import addon_bases, exclusive_variants, nested_archives
from omamods.omarchy_palette import OmarchyPalette
from omamods.mod_sites import AYAKA_SITE, NEXUS_SITE, PATCH_SITE, RELEASE_SITE
from omamods.staging import (
    StagedMod,
    list_staged_mods,
    load_staged_mod,
    mod_folder,
    forget_staged_mod,
    remove_staged_archive,
)


class ModsService:
    """Stage, install, and revert mods for the TUI; e.g. ``ModsService(host)``."""

    def __init__(self, host: TuiHost) -> None:
        self.host = host
        self.settings = self._load_settings()
        self.windows = NexusWindows(host.runner, host.launcher, host.browser)
        self.browser_downloads = BrowserDownloads(self)
        # Until the first scan, reuse the last one so queued downloads resolve.
        self.catalog = PakGameCatalog(load_detected_games(self.settings.storage_root))
        self.requirements = RequirementFlow(self)
        self.ayaka = AyakaSite(self)
        self.release = ReleaseSite(self)
        self.exe_patch = ExePatchSite(self)
        self.steam_setup = SteamSetup(self)
        self.conflicts = AssetConflicts(self)
        self.game_uninstall = GameUninstall(self)
        self.load_order = LoadOrderChoices(self)
        self.library_clean = LibraryClean(self)

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
        self.library_clean.audit(shelf)
        # The nxm handler runs in its own process and reads this file.
        save_detected_games(self.settings.storage_root, scanned)
        return shelf

    def full_recheck(self) -> GameShelf:
        """Rescan from scratch; e.g. ``shelf = service.full_recheck()``.

        Drops the cached Nexus game list so titles match again; the scan also
        refreshes ``library_clean.untracked``.
        """
        cache = self.settings.storage_root / "cache" / "nexus_games.json"
        cache.unlink(missing_ok=True)
        return self.shelf()

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
        builtin = self.exe_patch.staged_mods(game) + self.release.staged_mods(game)
        return builtin + nexus + self.ayaka.staged_mods(game)

    def staged_mod(
        self, game: PakOverlayGame, mod_id: int, site: str = NEXUS_SITE
    ) -> StagedMod:
        """Reload one mod; for example, ``service.staged_mod(sb, 1)``."""
        if site == AYAKA_SITE:
            return self.ayaka.staged_mod(game, mod_id)
        if site == RELEASE_SITE:
            return self.release.staged_mod(game, mod_id)
        if site == PATCH_SITE:
            return self.exe_patch.staged_mod(game, mod_id)
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
            self.browser_downloads.await_file(game, mod_id, file.file_id, required.url)
            return False
        return True

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
        if site == PATCH_SITE:
            return self.exe_patch.page_url(game)
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

    def addon_variants(
        self, archive: Path, variants: tuple[str, ...]
    ) -> Mapping[str, frozenset[str]]:
        """Find optional add-ons; e.g. ``service.addon_variants(archive, ('A', 'B'))``."""
        return addon_bases(self.host.reader.members(archive), variants)

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

    def forget_mod(
        self, game: PakOverlayGame, mod_id: int, site: str = NEXUS_SITE
    ) -> Path:
        """Take a mod with no downloads off the list; e.g. ``service.forget_mod(sb, 1)``."""
        if site not in (NEXUS_SITE, AYAKA_SITE):
            raise ValueError(f"site={site!r}: expected a Nexus or AyakaMods mod")
        return forget_staged_mod(self._root(site), game, mod_id)

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
        """Re-point an old or deleted handler here; e.g. ``service.refresh_outdated_nxm()``."""
        host = self.host
        outdated = nxm_entry_outdated(host.executable, host.applications)
        missing = host.mimeapps is not None and nxm_entry_missing(
            host.applications, host.mimeapps
        )
        if not (outdated or missing):
            return None
        return self.register_nxm()
