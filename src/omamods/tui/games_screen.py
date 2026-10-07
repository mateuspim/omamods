"""The home screen: pick a game, and set up the API key and nxm links."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from omamods.tui.mods_screen import ModsScreen
from omamods.tui.service import ModsService


def home_status(service: ModsService) -> str:
    """Summarise setup for the home screen; e.g. ``home_status(service)``."""
    key = "set" if service.has_api_key() else "missing - press K or :key <key>"
    return (
        f"Nexus API key: {key}\n"
        "Non-Premium downloads use the site's 'Mod Manager Download' button; "
        "press n once so those clicks land in OmaMods' staging folder.\n"
        "Vim keys: j/k move, gg/G top/bottom, h/l panes, : commands (:help), / search."
    )


class GamesScreen(Screen[None]):
    """Choose a game; e.g. ``app.push_screen(GamesScreen(service))``."""

    BINDINGS = [
        Binding("K", "app.prompt_api_key", "API key"),
        Binding("n", "app.register_nxm", "Handle nxm links"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, service: ModsService) -> None:
        super().__init__()
        self.service = service

    def compose(self) -> ComposeResult:
        yield Header()
        yield OptionList(
            *(Option(g.name, id=g.game_id) for g in self.service.games()), id="games"
        )
        yield Static(home_status(self.service), id="home-status", markup=False)
        yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        game = self.service.games()[event.option_index]
        self.app.push_screen(ModsScreen(self.service, game))

    def refresh_status(self) -> None:
        """Re-render setup state, e.g. after saving a key."""
        self.query_one("#home-status", Static).update(home_status(self.service))
