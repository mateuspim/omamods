"""The home screen: every detected game, its folder, and the setup checklist."""

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import OptionDoesNotExist

from omamods.game_shelf import GameShelf, ShelfEntry
from omamods.tui.dialogs import InfoDialog
from omamods.tui.list_filter import search_title
from omamods.tui.list_search import SearchableScreen
from omamods.tui.mods_screen import ModsScreen
from omamods.tui.service import ModsService
from omamods.tui.shelf_view import entry_detail, setup_summary, shelf_options

WELCOME = (
    "Pick a game on the left.\n\n"
    "Vim keys: j/k move, gg/G top/bottom, / filters (Esc clears), "
    ": commands (:help)."
)


class GamesScreen(SearchableScreen):
    """Choose a game; e.g. ``app.push_screen(GamesScreen(service))``."""

    BINDINGS = [
        Binding("o", "open_folder", "Open folder"),
        Binding("r", "rescan", "Rescan"),
        Binding("w", "show_warnings", "Warnings", show=False),
        Binding("K", "app.prompt_api_key", "API key"),
        Binding("n", "app.register_nxm", "Handle nxm links"),
        Binding("q", "app.quit", "Quit"),
        Binding("escape", "clear_search", "Clear filter", show=False),
    ]
    SEARCH_LIST_ID = "games"

    def __init__(self, service: ModsService) -> None:
        super().__init__()
        self.service = service
        self.shelf: GameShelf | None = None
        # Survives a filter that matches nothing, so clearing it finds the game.
        self.selected_key: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="home"):
            yield OptionList(id="games")
            with VerticalScroll(id="game-card", can_focus=False):
                yield Static(WELCOME, id="game-info", markup=False)
        yield Static(id="setup")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#games").border_title = "Games"
        self.query_one("#game-card").border_title = "Details"
        self.query_one("#setup").border_title = "Setup"
        self.action_rescan()

    def action_rescan(self) -> None:
        """Look for games again, e.g. after installing one in Steam."""
        self.query_one("#games", OptionList).loading = True
        self.refresh_status()
        self._scan()

    @work(thread=True, exclusive=True, group="shelf")
    def _scan(self) -> None:
        try:
            shelf = self.service.shelf()
        except (OSError, ValueError) as error:
            self.app.call_from_thread(self._scan_failed, error)
            return
        self.app.call_from_thread(self.show_shelf, shelf)

    def _scan_failed(self, error: Exception) -> None:
        self.query_one("#games", OptionList).loading = False
        self.notify(f"Game scan failed: {error}", severity="error", timeout=10)

    def show_shelf(self, shelf: GameShelf) -> None:
        """List a scan's games, keeping the cursor; e.g. ``screen.show_shelf(s)``."""
        self.shelf = shelf
        self.query_one("#games", OptionList).loading = False
        self.rebuild_list(jump_to_first=False)
        installed = sum(1 for entry in shelf.entries if entry.install)
        self.sub_title = (
            f"{installed} installed · {len(shelf.libraries)} Steam libraries"
        )
        self.refresh_status()

    def rebuild_list(self, jump_to_first: bool) -> int:
        """List the games matching ``search_query``; e.g. ``screen.rebuild_list(True)``."""
        games = self.query_one("#games", OptionList)
        options = shelf_options(self.shelf, self.search_query) if self.shelf else []
        games.clear_options()
        games.add_options(options)
        games.action_first()
        if self.selected_key is not None and not jump_to_first:
            self._highlight(self.selected_key)
        if games.highlighted_option is not None:
            self.selected_key = games.highlighted_option.id
        shown = sum(1 for option in options if not option.disabled)
        total = len(self.shelf.entries) if self.shelf else 0
        games.border_title = search_title("Games", self.search_query, shown, total)
        return shown

    def _highlight(self, key: str) -> None:
        games = self.query_one("#games", OptionList)
        try:
            games.highlighted = games.get_option_index(key)
        except OptionDoesNotExist:
            return

    def entry(self, key: str | None) -> ShelfEntry | None:
        """Find a listed game by option ID; e.g. ``screen.entry('cronos')``."""
        if self.shelf is None or key is None:
            return None
        return next((e for e in self.shelf.entries if e.key == key), None)

    def selected_entry(self) -> ShelfEntry | None:
        """Return the highlighted game; e.g. ``screen.selected_entry().name``."""
        games = self.query_one("#games", OptionList)
        option = games.highlighted_option
        return self.entry(option.id if option else None)

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        entry = self.entry(event.option.id)
        if entry is not None:
            self.selected_key = entry.key
            card = entry_detail(entry, self._staged_count(entry))
            self.query_one("#game-info", Static).update(card)

    def _staged_count(self, entry: ShelfEntry) -> int | None:
        if entry.pak_game is None:
            return None
        try:
            return len(self.service.staged_mods(entry.pak_game))
        except (OSError, ValueError):
            return None

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.action_open_game()

    def action_open_game(self) -> None:
        """Manage the highlighted game's mods, when OmaMods can install them."""
        entry = self.selected_entry()
        if entry is None:
            return
        if entry.pak_game is None:
            self.notify(f"{entry.name}: installing mods is not supported yet.")
            return
        self.app.push_screen(ModsScreen(self.service, entry.pak_game))

    def action_open_folder(self) -> None:
        """Open the highlighted game's install folder in the file manager."""
        entry = self.selected_entry()
        install = entry.install if entry else None
        if install is None:
            self.notify("This game is not installed, so it has no folder yet.")
            return
        self.service.open_folder(install.install_path)

    def action_show_warnings(self) -> None:
        warnings = self.shelf.warnings if self.shelf else ()
        text = "\n\n".join(warnings) or "No discovery warnings."
        self.app.push_screen(InfoDialog("Discovery warnings", text))

    def refresh_status(self) -> None:
        """Re-render setup state, e.g. after saving a key."""
        summary = setup_summary(self.shelf, self.service.has_api_key())
        self.query_one("#setup", Static).update(summary)
