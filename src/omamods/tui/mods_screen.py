"""One game's staging folder: browse mods, stage files, install, and revert."""

import asyncio
from collections.abc import Callable
from typing import TypeVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from omamods.mod_plan import (
    FilePlan,
    conflicting_targets,
    default_installs,
    describe_plans,
)
from omamods.nexus_api import NexusFile, describe_nexus_file
from omamods.pak_games import PakOverlayGame
from omamods.staging import StagedMod
from omamods.tui.mods_commands import MODS_COMMANDS, run_mods_command
from omamods.tui.dialogs import ChoiceDialog, ConfirmDialog, FilePicker, TextPrompt
from omamods.tui.preview import PicturePreview
from omamods.tui.service import ModsService

Result = TypeVar("Result")
REFRESH_SECONDS = 3.0
BROWSER_HINT = (
    "{name}: click 'Mod Manager Download' in the Nexus window; "
    "it closes when all chosen files have arrived."
)


def describe_mod(mod: StagedMod) -> str:
    """Render the details panel; for example, ``describe_mod(staged)``."""
    if mod.info is None:
        return f"{mod.title}\nNo page details yet; press a and paste its URL."
    info = mod.info
    byline = " · ".join(part for part in (info.author, info.version) if part)
    return f"{info.name}\n{byline}\n\n{info.summary}".strip()


def file_cells(mod: StagedMod, file: NexusFile) -> tuple[str, ...]:
    """Render one file row; for example, ``file_cells(staged, file)``."""
    size = f"{file.size_kb / 1024:.1f} MB" if file.size_kb else ""
    # Status first: long Nexus file names used to push it off-screen.
    return (
        "yes" if file.file_id in mod.installed else "",
        "yes" if file.file_id in mod.archives else "",
        file.category,
        file.version,
        size,
        file.display_name or file.file_name,
        str(file.file_id),
    )


class ModsScreen(Screen[None]):
    """Show and change one game's mods; e.g. ``app.push_screen(ModsScreen(s, sb))``."""

    BINDINGS = [
        Binding("a", "add", "Add mod URL"),
        Binding("d", "download", "Download file"),
        Binding("i", "install_mod", "Install mod"),
        Binding("u", "uninstall_mod", "Uninstall mod"),
        Binding("x", "remove_staged", "Remove download"),
        Binding("o", "open_picture", "Full picture"),
        Binding("w", "open_page", "Web page"),
        Binding("escape", "app.pop_screen", "Back"),
        Binding("n", "next_match(1)", "Next match", show=False),
        Binding("N", "next_match(-1)", "Previous match", show=False),
    ]
    SCREEN_COMMANDS = MODS_COMMANDS

    def __init__(self, service: ModsService, game: PakOverlayGame) -> None:
        super().__init__()
        self.service = service
        self.game = game
        self.mods: tuple[StagedMod, ...] = ()
        self.current: StagedMod | None = None
        self.search_text = ""
        self.picture_attempts: set[int] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield OptionList(id="mods")
            # Not focusable, so h/l (and Tab) go straight from the mod list to
            # the file table instead of stopping on this pane first.
            with VerticalScroll(id="detail", can_focus=False):
                yield PicturePreview(id="picture")
                yield Static(id="details", markup=False)
                yield DataTable(id="files", cursor_type="row")
        yield Static(id="status", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = self.game.name
        self.query_one("#mods").border_title = "Mods"
        self.query_one("#detail").border_title = "Details"
        table = self.query_one("#files", DataTable)
        table.add_columns(
            "Installed", "Staged", "Category", "Version", "Size", "File", "ID"
        )
        folder = self.service.staging_folder(self.game)
        self.query_one("#status", Static).update(
            f"Enter on a file installs or uninstalls just that file · Staging: {folder}"
        )
        self.reload()
        self.set_interval(REFRESH_SECONDS, self.reload)

    def reload(self) -> None:
        """Pick up downloads finished elsewhere, e.g. by an nxm click."""
        mods = self._attempt(lambda: self.service.staged_mods(self.game))
        if mods is None or mods == self.mods:
            return
        self.mods = mods
        selected = self.current.mod_id if self.current else None
        mod_list = self.query_one("#mods", OptionList)
        mod_list.clear_options()
        mod_list.add_options(Option(m.title, id=str(m.mod_id)) for m in mods)
        ids = [m.mod_id for m in mods]
        if mods:
            mod_list.highlighted = ids.index(selected) if selected in ids else 0

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        self._show(self.mods[event.option_index])

    def _show(self, mod: StagedMod) -> None:
        previous = self.current
        self.current = mod
        if previous is None or previous.picture != mod.picture:
            self.query_one("#picture", PicturePreview).show(mod.picture)
        self._backfill_picture(mod)
        self.query_one("#details", Static).update(describe_mod(mod))
        table = self.query_one("#files", DataTable)
        row = table.cursor_row
        table.clear()
        for file in mod.files:
            table.add_row(*file_cells(mod, file), key=str(file.file_id))
        if mod.files:
            table.move_cursor(row=min(row, len(mod.files) - 1))

    def _backfill_picture(self, mod: StagedMod) -> None:
        # Mods staged before pictures worked (or while offline) fetch theirs once.
        lacks = mod.picture is None and mod.info and mod.info.picture_url
        if lacks and mod.mod_id not in self.picture_attempts:
            self.picture_attempts.add(mod.mod_id)
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

    def _attempt(self, action: Callable[[], Result]) -> Result | None:
        try:
            return action()
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)
            return None

    def _selected_file(self) -> NexusFile | None:
        if self.current is None or not self.current.files:
            self.notify("Add a mod first (a) and pick one of its files.")
            return None
        return self.current.files[self.query_one("#files", DataTable).cursor_row]

    def action_add(self) -> None:
        prompt = TextPrompt(
            f"Paste a {self.game.name} Nexus mod URL",
            f"https://www.nexusmods.com/{self.game.nexus_domain}/mods/1",
        )
        self.app.push_screen(prompt, self.fetch_url)

    def fetch_url(self, url: str | None) -> None:
        """Fetch a mod page into staging; for example, ``screen.fetch_url(url)``."""
        if url:
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
        else:
            self.download_files(self.current.mod_id, (file,))

    async def _plan_file(self, mod: StagedMod, file: NexusFile) -> FilePlan | None:
        archive = mod.archives[file.file_id]
        variants = self._attempt(lambda: self.service.variants(self.game, archive))
        if variants is None:
            return None
        option = None
        if variants:
            title = f"{file.file_name} has variants; pick one"
            option = await self.app.push_screen_wait(ChoiceDialog(title, variants))
            if option is None:
                return None
        assets = self._attempt(lambda: self.service.plan(self.game, archive, option))
        return None if assets is None else FilePlan(file, option, assets)

    async def _plan_files(
        self, mod: StagedMod, files: tuple[NexusFile, ...]
    ) -> tuple[FilePlan, ...] | None:
        plans: list[FilePlan] = []
        for file in files:
            plan = await self._plan_file(mod, file)
            if plan is None:
                return None
            plans.append(plan)
        return tuple(plans)

    @work
    async def install_files(self, mod: StagedMod, files: tuple[NexusFile, ...]) -> None:
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
        if await self.app.push_screen_wait(ConfirmDialog(title, describe_plans(plans))):
            await asyncio.to_thread(self._install_plans, mod.mod_id, plans)
            self.reload()

    def _install_plans(self, mod_id: int, plans: tuple[FilePlan, ...]) -> None:
        for plan in plans:
            count = self._attempt(
                lambda: self.service.install(
                    self.game, mod_id, plan.file.file_id, plan.option
                )
            )
            if count is None:
                return
            self.notify(f"Installed {count} files from {plan.file.file_name}")

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
        self.app.push_screen(
            dialog, lambda yes: yes and self._uninstall(mod.mod_id, files)
        )

    def _uninstall(self, mod_id: int, files: tuple[NexusFile, ...]) -> None:
        for file in files:
            count = self._attempt(
                lambda: self.service.revert(self.game, mod_id, file.file_id)
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
        mod_id = self.current.mod_id
        dialog = ConfirmDialog(
            f"Delete the download {file.file_name}?",
            f"{describe_nexus_file(file)}\nThe game is not touched.",
        )
        self.app.push_screen(dialog, lambda yes: yes and self._remove(mod_id, file))

    def _remove(self, mod_id: int, file: NexusFile) -> None:
        removed = self._attempt(
            lambda: self.service.remove_staged(self.game, mod_id, file.file_id)
        )
        if removed is not None:
            self.notify(f"Deleted {removed.name}")
        self.reload()

    def run_command(self, name: str, args: tuple[str, ...]) -> None:
        """Run a ':' command; for example, ``screen.run_command('install', ())``."""
        run_mods_command(self, name, args)

    def search(self, text: str) -> None:
        """Jump to the first mod whose name contains ``text``, like vim's '/'."""
        self.search_text = text.lower()
        self._jump_to_match(1, include_current=True)

    def action_next_match(self, step: int) -> None:
        if not self.search_text:
            self.notify("E35: No previous regular expression; press / to search")
            return
        self._jump_to_match(step, include_current=False)

    def _jump_to_match(self, step: int, include_current: bool) -> None:
        mod_list = self.query_one("#mods", OptionList)
        start = mod_list.highlighted or 0
        offsets = range(0 if include_current else 1, len(self.mods) + 1)
        for offset in offsets:
            index = (start + step * offset) % max(len(self.mods), 1)
            if self.search_text in self.mods[index].title.lower():
                mod_list.highlighted = index
                return
        self.notify(f"E486: Pattern not found: {self.search_text}", severity="warning")

    def action_open_picture(self) -> None:
        if self.current is None or self.current.picture is None:
            self.notify("No picture for this mod.")
            return
        picture = self.current.picture
        self._attempt(lambda: self.service.open_picture(picture))

    def action_open_page(self) -> None:
        if self.current is not None:
            url = self.service.mod_page_url(self.game, self.current.mod_id)
            self._attempt(lambda: self.service.open_url(url))
