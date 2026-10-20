"""One game's staging folder: browse mods, stage files, install, and revert."""

import asyncio
from pathlib import Path
from rich.text import Text

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import DataTable, OptionList, Static
from textual.widgets.option_list import Option

from omamods.mod_plan import (
    FilePlan,
    conflicting_targets,
    default_installs,
    describe_plans,
)
from omamods.ayaka_pages import is_ayaka_url
from omamods.nexus_api import NexusFile, describe_nexus_file
from omamods.pak_games import PakOverlayGame
from omamods.mod_sites import AYAKA_SITE, NEXUS_SITE, RELEASE_SITE
from omamods.staging import StagedMod
from omamods.adult_marks import BLUR
from omamods.tui.adult_actions import AdultScreen
from omamods.tui.mods_commands import MODS_COMMANDS, run_mods_command
from omamods.tui.dialogs import ConfirmDialog, FilePicker, TextPrompt, VariantPicker
from omamods.tui.list_filter import no_match_option, search_title
from omamods.tui.mod_rows import (
    describe_mod,
    mod_key,
    mod_prompt,
    visible_mods,
)
from omamods.tui.list_search import SearchableScreen
from omamods.tui.downloads_panel import (
    FULL_QUEUE,
    MINIMIZED,
    DownloadsPanel,
    next_panel_mode,
)
from omamods.tui.preview import PicturePreview
from omamods.tui.service import ModsService
from omamods.tui.requirement_actions import ERROR_TOAST_SECONDS
from omamods.tui.toast_filter import RepeatedToastFilter
from omamods.tui.uninstall_all_actions import UninstallAllScreen
from omamods.tui.mod_detail import ModDetail
from omamods.tui.mod_inspector import collision_warning
from omamods.tui.workspace import WorkspaceHeader, WorkspaceHints, WorkspaceStatus

REFRESH_SECONDS = 3.0
BROWSER_HINT = (
    "{name}: click 'Mod Manager Download' in the Nexus window; "
    "it closes when all chosen files have arrived."
)


class ModsScreen(SearchableScreen, UninstallAllScreen, AdultScreen):
    """Show and change one game's mods; e.g. ``app.push_screen(ModsScreen(s, sb))``."""

    BINDINGS = [
        Binding("a", "add", "Add mod URL"),
        Binding("d", "download", "Download file"),
        Binding("i", "install_mod", "Install mod"),
        Binding("u", "uninstall_mod", "Uninstall mod"),
        Binding("U", "uninstall_all", "Uninstall all mods"),
        Binding("x", "remove_staged", "Remove download"),
        Binding("o", "open_picture", "Full picture"),
        Binding("w", "open_page", "Web page"),
        Binding("L", "launch_options", "Launch options", show=False),
        # Overrides the app's D (open the queue screen): grows the panel instead.
        Binding("D", "cycle_downloads", "Downloads size"),
        Binding("escape", "back", "Back"),
        Binding("n", "next_match(1)", "Next match", show=False),
        Binding("N", "next_match(-1)", "Previous match", show=False),
        Binding("H", "cycle_adult", "NSFW blur/hide/show"),
        Binding("m", "mark_adult", "Mark NSFW", show=False),
        Binding("p", "toggle_preview", "Toggle preview", show=False),
    ]
    SCREEN_COMMANDS = MODS_COMMANDS
    SEARCH_LIST_ID = "mods"

    def __init__(self, service: ModsService, game: PakOverlayGame) -> None:
        super().__init__()
        self.service = service
        self.game = game
        self.mods: tuple[StagedMod, ...] = ()
        # The mods matching the '/' filter, in list order.
        self.shown: tuple[StagedMod, ...] = ()
        self.current: StagedMod | None = None
        self.picture_attempts: set[str] = set()
        # Set from the first i until its dialog closes, so repeats are ignored.
        self.checking_requirements = False
        self.error_toasts = RepeatedToastFilter(ERROR_TOAST_SECONDS)

    def compose(self) -> ComposeResult:
        yield WorkspaceHeader(self.game.name, "MOD WORKSPACE")
        with Horizontal(id="mods-body"):
            yield OptionList(
                Option("No mods yet.\n\na  Add your first mod", disabled=True),
                id="mods",
            )
            # Not focusable, so h/l (and Tab) go straight from the mod list to
            # the file table instead of stopping on this pane first.
            yield ModDetail(self.service, self.game)
        yield DownloadsPanel(self.service, self.game)
        yield Static(id="status", markup=False)
        yield WorkspaceStatus(self.game.name)
        yield WorkspaceHints(
            "[b]a[/] add   [b]i[/] install   [b]enter[/] file   [b]/[/] find   "
            "[b]p[/] preview   [b]D[/] downloads   [b]U[/] uninstall all"
        )

    def action_toggle_preview(self) -> None:
        """Make room for artwork or files; e.g. ``screen.action_toggle_preview()``."""
        show = not self.query_one("#preview-pane").display
        self.set_class(not show, "preview-hidden")
        self.set_class(show, "preview-requested")

    def on_mount(self) -> None:
        self.sub_title = self.game.name
        self.query_one("#mods").border_title = "Mods"
        self.query_one("#detail").border_title = "Mod files"
        self.query_one("#preview-pane").border_title = "Inspector"
        folder = self.service.staging_folder(self.game)
        self.query_one("#status", Static).update(
            f"Enter on a file installs or uninstalls just that file · Staging: {folder}"
        )
        self.load_adult_marks()
        self.reload()
        self.set_interval(REFRESH_SECONDS, self.reload)
        self.set_interval(REFRESH_SECONDS, self.take_ayaka_arrivals)
        if self.game.steam_app_id is not None:
            self._warn_launch_options()
        self.check_release_updates()
        panel = self.query_one(DownloadsPanel)
        self.set_interval(REFRESH_SECONDS, panel.refresh_queue)

    def action_cycle_downloads(self) -> None:
        self.show_downloads(next_panel_mode(self.query_one(DownloadsPanel).mode))

    def show_downloads(self, mode: str) -> None:
        """Size the downloads panel; for example, ``screen.show_downloads('full')``."""
        self.query_one(DownloadsPanel).set_mode(mode)
        # Full hides the mods, so focus must leave them (and come back after).
        self.set_class(mode == FULL_QUEUE, "downloads-full")
        if mode == MINIMIZED:
            self.query_one("#mods", OptionList).focus()
        elif mode == FULL_QUEUE:
            self.query_one("#downloads-table", DataTable).focus()

    def reload(self) -> None:
        """Pick up downloads finished elsewhere, e.g. by an nxm click."""
        mods = self._attempt(lambda: self.service.staged_mods(self.game))
        if mods is None or mods == self.mods:
            return
        self.mods = mods
        self.rebuild_list(jump_to_first=False)

    def rebuild_list(self, jump_to_first: bool) -> int:
        """List the mods matching ``search_query``; e.g. ``screen.rebuild_list(True)``."""
        hidden = self.hidden_mod_keys()
        self.shown = visible_mods(self.mods, self.search_query, hidden)
        mod_list = self.query_one("#mods", OptionList)
        mod_list.clear_options()
        mod_list.add_options(self._mod_options())
        self._title_mod_list(mod_list, len(hidden))
        ids = [mod_key(m) for m in self.shown]
        selected = mod_key(self.current) if self.current else None
        if ids:
            keep = selected in ids and not jump_to_first
            mod_list.highlighted = ids.index(selected) if keep else 0
        return len(ids)

    def _mod_options(self) -> list[Option]:
        query = self.search_query
        options = [
            Option(mod_prompt(m, query, self.mod_is_adult(m)), id=mod_key(m))
            for m in self.shown
        ]
        if query and not options:
            options.append(no_match_option(query))
        return options

    def _title_mod_list(self, mod_list: OptionList, hidden: int) -> None:
        shown, total = len(self.shown), len(self.mods)
        mod_list.border_title = search_title("Mods", self.search_query, shown, total)
        mod_list.border_subtitle = (
            f"{hidden} NSFW hidden · H shows them"
            if hidden
            else f"{sum(bool(mod.installed) for mod in self.mods)} installed · {len(self.mods)} staged"
        )

    def action_back(self) -> None:
        """Esc clears an active '/' filter first, then leaves the screen."""
        if self.search_query:
            self.action_clear_search()
            return
        self.app.pop_screen()

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        # Look up by ID: a fast '/' may re-list the mods before this event lands.
        by_key = {mod_key(m): m for m in self.shown}
        if event.option.id in by_key:
            self._show(by_key[event.option.id])

    def _show(self, mod: StagedMod) -> None:
        self.current = mod
        blurred = self.adult.mode == BLUR and self.mod_is_adult(mod)
        self.query_one("#picture", PicturePreview).show(mod.picture, blurred)
        self._backfill_picture(mod)
        details = Text(describe_mod(mod, self.mod_is_adult(mod)))
        details.stylize("bold", 0, len(mod.title))
        self.query_one("#details", Static).update(details)
        self.query_one(ModDetail).show_mod(mod)

    def _backfill_picture(self, mod: StagedMod) -> None:
        # Mods staged before pictures worked (or while offline) fetch theirs once.
        if mod.picture is not None or mod_key(mod) in self.picture_attempts:
            return
        if mod.info is not None and mod.info.picture_url is None:
            return
        # Hand-staged mods (`omamods nexus install`) have no page details yet.
        nexus = mod.site == NEXUS_SITE
        if mod.info is None and nexus and not self.service.has_api_key():
            return
        self.picture_attempts.add(mod_key(mod))
        self._picture_worker(mod)

    @work(thread=True)
    def _picture_worker(self, mod: StagedMod) -> None:
        try:
            self.service.fetch_missing_picture(self.game, mod)
        except (OSError, ValueError) as error:
            self.notify(
                f"{mod.title}: picture unavailable ({error})", severity="warning"
            )
            return
        self.app.call_from_thread(self.reload)

    def _selected_file(self) -> NexusFile | None:
        if self.current is None or not self.current.files:
            self.notify("Add a mod first (a) and pick one of its files.")
            return None
        return self.current.files[self.query_one("#files", DataTable).cursor_row]

    def action_add(self) -> None:
        prompt = TextPrompt(
            f"Paste a {self.game.name} mod URL from Nexus or AyakaMods",
            f"https://www.nexusmods.com/{self.game.nexus_domain}/mods/1",
        )
        self.app.push_screen(prompt, self.fetch_url)

    def fetch_url(self, url: str | None) -> None:
        """Fetch a mod page into staging; for example, ``screen.fetch_url(url)``."""
        if url and is_ayaka_url(url.strip()):
            self.fetch_ayaka(url)
        elif url:
            self.notify("Fetching mod details from Nexus...")
            self._fetch_worker(url)

    @work(thread=True)
    def _fetch_worker(self, url: str) -> None:
        mod = self._attempt(lambda: self.service.fetch_mod(self.game, url))
        if mod is not None:
            self.app.call_from_thread(self._pick_files, mod)

    def _pick_files(self, mod: StagedMod) -> None:
        self.reload()
        picker = FilePicker(f"{mod.title}: choose files to stage", mod.files)
        self.app.push_screen(picker, lambda files: self._download(mod, files))

    def _download(self, mod: StagedMod, files: tuple[NexusFile, ...] | None) -> None:
        if files:
            self.download_files(mod.mod_id, files)

    @work(thread=True)
    def download_files(self, mod_id: int, files: tuple[NexusFile, ...]) -> None:
        self._attempt(lambda: self.service.mark_queued(self.game, mod_id, files))
        self.notify(f"Downloading {len(files)} file(s); press D to watch the queue.")
        for file in files:
            staged = self._attempt(
                lambda: self.service.fetch_file(self.game, mod_id, file)
            )
            if staged is False:
                self.notify(BROWSER_HINT.format(name=file.file_name), timeout=15)
        self.app.call_from_thread(self.reload)

    def action_download(self) -> None:
        if self.current is not None and self.current.site == AYAKA_SITE:
            self.download_ayaka(self.current)  # Its files, or its page.
            return
        if self.current is not None and self.current.site == RELEASE_SITE:
            self.download_release(self.current)  # The newest release's.
            return
        file = self._selected_file()
        if file is not None and self.current is not None:
            self.download_files(self.current.mod_id, (file,))

    def action_install_mod(self) -> None:
        if self.current is None:
            return
        files = default_installs(self.current)
        if not files:
            self.notify(
                "Nothing new to install: every staged MAIN/UPDATE file is installed. "
                "Press Enter on an optional file to add it."
            )
            return
        self.install_files(self.current, files)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        file = self._selected_file()
        if file is None or self.current is None:
            return
        if file.file_id in self.current.installed:
            self.confirm_uninstall(self.current, (file,))
        elif file.file_id in self.current.archives:
            self.install_files(self.current, (file,))
        elif self.current.site == RELEASE_SITE:
            self.download_release(self.current)
        else:
            self.download_files(self.current.mod_id, (file,))

    async def _chosen_variants(
        self, file: NexusFile, archive: Path
    ) -> tuple[str | None, ...] | None:
        variants = self._attempt(lambda: self.service.variants(self.game, archive))
        if not variants:
            return None if variants is None else (None,)
        title = f"{file.file_name} has variants; pick which to install"
        exclusive = self._attempt(
            lambda: self.service.exclusive_variants(archive, variants)
        )
        picker = VariantPicker(title, variants, exclusive)
        return await self.app.push_screen_wait(picker)

    def _warn_nested(self, file: NexusFile, archive: Path) -> None:
        nested = self._attempt(lambda: self.service.nested_archives(archive))
        if nested:
            self.notify(
                f"Not installed from {file.file_name}, archives inside the "
                f"archive: {', '.join(nested)}",
                severity="warning",
                timeout=15,
            )

    async def _plan_file(
        self, mod: StagedMod, file: NexusFile
    ) -> tuple[FilePlan, ...] | None:
        archive = mod.archives[file.file_id]
        options = await self._chosen_variants(file, archive)
        if options is None:
            return None
        self._warn_nested(file, archive)
        plans: list[FilePlan] = []
        for option in options:
            assets = self._attempt(
                lambda: self.service.plan(self.game, archive, option)
            )
            if assets is None:
                return None
            plans.append(FilePlan(file, option, assets))
        return tuple(plans)

    async def _plan_files(
        self, mod: StagedMod, files: tuple[NexusFile, ...]
    ) -> tuple[FilePlan, ...] | None:
        plans: list[FilePlan] = []
        for file in files:
            planned = await self._plan_file(mod, file)
            if planned is None:
                return None
            plans.extend(planned)
        return tuple(plans)

    @work
    async def install_now(self, mod: StagedMod, files: tuple[NexusFile, ...]) -> None:
        plans = await self._plan_files(mod, files)
        if plans is None:
            return
        conflicts = conflicting_targets(plans)
        if conflicts:
            self.notify(
                "These files write the same game file; install one of them with "
                "Enter instead:\n" + "\n".join(conflicts),
                severity="error",
                timeout=15,
            )
            return
        title = f"Install {len(plans)} file(s) of {mod.title}?"
        report = await asyncio.to_thread(
            self.service.conflicts.for_plans, self.game, mod, plans
        )
        details = describe_plans(plans, self.game.folder_label())
        details += collision_warning(report, mod.title)
        if await self.app.push_screen_wait(ConfirmDialog(title, details)):
            await asyncio.to_thread(self._install_plans, mod, plans)
            self.reload()
            # A UE4SS bundle or ASI plugin does nothing until Proton loads its
            # proxy DLL.
            beside_exe = any(a.beside_exe for plan in plans for a in plan.assets)
            loads_dll = beside_exe or self.game.asi_loader
            if loads_dll and self.game.steam_app_id is not None:
                self._warn_launch_options()

    def _install_plans(self, mod: StagedMod, plans: tuple[FilePlan, ...]) -> None:
        for plan in plans:
            count = self._attempt(
                lambda: self.service.install(
                    self.game, mod.mod_id, plan.file.file_id, plan.option, mod.site
                )
            )
            if count is None:
                return
            variant = f" ({plan.option})" if plan.option else ""
            self.notify(f"Installed {count} files from {plan.file.file_name}{variant}")

    def action_uninstall_mod(self) -> None:
        if self.current is None:
            return
        files = tuple(
            f for f in self.current.files if f.file_id in self.current.installed
        )
        if not files:
            self.notify("Nothing from this mod is installed.")
            return
        self.confirm_uninstall(self.current, files)

    def confirm_uninstall(self, mod: StagedMod, files: tuple[NexusFile, ...]) -> None:
        names = "\n".join(f"  {file.file_name}" for file in files)
        dialog = ConfirmDialog(f"Uninstall from {mod.title}?", names)
        self.app.push_screen(dialog, lambda yes: yes and self._uninstall(mod, files))

    def _uninstall(self, mod: StagedMod, files: tuple[NexusFile, ...]) -> None:
        for file in files:
            count = self._attempt(
                lambda: self.service.revert(
                    self.game, mod.mod_id, file.file_id, mod.site
                )
            )
            if count is None:
                break
            self.notify(f"Removed {count} files of {file.file_name}")
        self.reload()

    def action_remove_staged(self) -> None:
        file = self._selected_file()
        if file is None or self.current is None:
            return
        self.confirm_remove(file)

    def confirm_remove(self, file: NexusFile) -> None:
        """Ask, then delete a download; for example, ``screen.confirm_remove(file)``."""
        if self.current is None or file.file_id not in self.current.archives:
            self.notify("This file is not downloaded.")
            return
        mod = self.current
        dialog = ConfirmDialog(
            f"Delete the download {file.file_name}?",
            f"{describe_nexus_file(file)}\nThe game is not touched.",
        )
        self.app.push_screen(dialog, lambda yes: yes and self._remove(mod, file))

    def _remove(self, mod: StagedMod, file: NexusFile) -> None:
        removed = self._attempt(
            lambda: self.service.remove_staged(
                self.game, mod.mod_id, file.file_id, mod.site
            )
        )
        if removed is not None:
            self.notify(f"Deleted {removed.name}")
        self.reload()

    def run_command(self, name: str, args: tuple[str, ...]) -> None:
        """Run a ':' command; for example, ``screen.run_command('install', ())``."""
        run_mods_command(self, name, args)

    def action_open_picture(self) -> None:
        if self.current is None or self.current.picture is None:
            self.notify("No picture for this mod.")
            return
        picture = self.current.picture
        self._attempt(lambda: self.service.open_picture(picture))

    def action_open_page(self) -> None:
        if self.current is not None:
            current = self.current
            url = self.service.mod_page_url(self.game, current.mod_id, current.site)
            self._attempt(lambda: self.service.open_url(url))
