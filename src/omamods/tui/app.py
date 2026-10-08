"""The OmaMods terminal UI: pick a game, then stage and install its mods."""

import time
from collections.abc import Callable

from textual import work
from textual.app import App
from textual.binding import Binding

from omamods.ayaka_pages import is_ayaka_url
from omamods.nexus_api import parse_nexus_page
from omamods.pak_games import PakOverlayGame
from omamods.tui.commands import (
    GLOBAL_COMMANDS,
    CommandSpec,
    find_game,
    help_text,
    parse_command,
    resolve_command,
)
from omamods.tui.dialogs import CommandPrompt, InfoDialog, TextPrompt
from omamods.tui.downloads_screen import DownloadsScreen
from omamods.tui.games_screen import GamesScreen
from omamods.tui.login_dialog import LoginCookiePrompt
from omamods.tui.mods_screen import ModsScreen
from omamods.tui.service import ModsService
from omamods.tui.styles import APP_CSS, DEFAULT_THEME
from omamods.tui.vim import ChordTracker, run_motion

BROWSER_POLL_SECONDS = 2.0


def one_argument(args: tuple[str, ...], usage: str) -> str:
    """Require one argument; for example, ``one_argument(('sb',), ':game <name>')``."""
    if len(args) != 1:
        raise ValueError(f"{usage}: expected one argument, got {list(args)}")
    return args[0]


class OmaModsApp(App[None]):
    """Run the TUI; for example, ``OmaModsApp(service).run()``."""

    CSS = APP_CSS
    TITLE = "OmaMods"
    BINDINGS = [
        Binding("D", "downloads", "Downloads"),
        Binding("colon", "command_line", ":cmd"),
        Binding("slash", "search", "/search", show=False),
        Binding("j", "motion('down')", show=False),
        Binding("k", "motion('up')", show=False),
        Binding("G", "motion('bottom')", show=False),
        Binding("g", "vim_g", show=False),
        Binding("ctrl+d", "motion('page_down')", show=False),
        Binding("ctrl+u", "motion('page_up')", show=False),
        Binding("h", "focus_previous", show=False),
        Binding("l", "focus_next", show=False),
    ]

    def __init__(self, service: ModsService) -> None:
        super().__init__()
        self.service = service
        self.chord = ChordTracker()
        self.theme = DEFAULT_THEME

    def on_mount(self) -> None:
        self.push_screen(GamesScreen(self.service))
        self.set_interval(BROWSER_POLL_SECONDS, self.advance_browser_downloads)
        self.set_interval(BROWSER_POLL_SECONDS, self.tick_requirements)

    def tick_requirements(self) -> None:
        """Install requirement downloads as they arrive; runs on a timer."""
        if self.service.requirements.has_work:
            self.advance_requirements()

    @work(thread=True, group="requirements")
    def advance_requirements(self) -> None:
        # Installs copy whole archives, so they stay off the UI thread.
        try:
            messages = self.service.requirements.advance()
        except (OSError, ValueError) as error:
            self.notify(
                f"Stopped installing requirements: {error}",
                severity="error",
                timeout=15,
            )
            return
        for message in messages:
            self.notify(message, timeout=8)

    def advance_browser_downloads(self) -> None:
        """Step Nexus windows through queued files; runs on a timer on every screen."""
        try:
            messages = self.service.advance_browser_downloads()
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error")
            return
        for message in messages:
            self.notify(message, timeout=8)

    def action_downloads(self) -> None:
        """Open the queue from any screen; for example, ``app.action_downloads()``."""
        if not isinstance(self.screen, DownloadsScreen):
            self.push_screen(DownloadsScreen(self.service))

    def action_motion(self, motion: str) -> None:
        """Move the focused list like vim; e.g. ``app.action_motion('down')``."""
        run_motion(self.focused, motion)

    def action_vim_g(self) -> None:
        if self.chord.press(time.monotonic()):
            run_motion(self.focused, "top")

    def _screen_commands(self) -> tuple[CommandSpec, ...]:
        return GLOBAL_COMMANDS + getattr(self.screen, "SCREEN_COMMANDS", ())

    def action_command_line(self) -> None:
        words = tuple(spec.name for spec in self._screen_commands())
        self.push_screen(CommandPrompt(":", words), self.run_command_line)

    def action_search(self) -> None:
        if hasattr(self.screen, "search"):
            self.push_screen(CommandPrompt("/", ()), self._search)

    def _search(self, text: str | None) -> None:
        if text:
            self.screen.search(text)

    def run_command_line(self, text: str | None) -> None:
        """Run a ':' line on the current screen; e.g. ``app.run_command_line('q')``."""
        try:
            parsed = parse_command(text or "")
            if parsed is None:
                return
            spec = resolve_command(parsed.word, self._screen_commands())
            handler = self._global_handlers().get(spec.name)
            if handler is None:
                self.screen.run_command(spec.name, parsed.args)
            else:
                handler(parsed.args)
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)

    def _global_handlers(self) -> dict[str, Callable[[tuple[str, ...]], None]]:
        return {
            "quit": lambda args: self._quit_screen(),
            "quitall": lambda args: self.exit(),
            "help": lambda args: self._show_help(),
            "game": lambda args: self._open_game(one_argument(args, ":game <name>")),
            "queue": lambda args: self.action_downloads(),
            "key": lambda args: self.save_api_key(one_argument(args, ":key <api-key>")),
            "nxm": lambda args: self.action_register_nxm(),
            "add": lambda args: self.add_mod(one_argument(args, ":add <url>")),
            "ayaka-login": self._ayaka_login_command,
        }

    def _quit_screen(self) -> None:
        if isinstance(self.screen, GamesScreen):
            self.exit()
        else:
            self.pop_screen()

    def _show_help(self) -> None:
        self.push_screen(InfoDialog("Commands", help_text(self._screen_commands())))

    def _open_game(self, query: str) -> ModsScreen:
        game = find_game(self.service.games(), query)
        if isinstance(self.screen, ModsScreen) and self.screen.game == game:
            return self.screen
        screen = ModsScreen(self.service, game)
        self.push_screen(screen)
        return screen

    def add_mod(self, url: str) -> None:
        """Open the URL's game and fetch the mod; e.g. ``app.add_mod('https://...')``."""
        if is_ayaka_url(url):
            # Ayaka links name no game; its page says which one.
            self._add_ayaka_mod(url)
            return
        game = self.service.catalog.for_domain(parse_nexus_page(url).domain)
        self._fetch_into(game, url)

    def _fetch_into(self, game: PakOverlayGame, url: str) -> None:
        screen = self._open_game(game.game_id)
        screen.call_after_refresh(screen.fetch_url, url)

    @work(thread=True)
    def _add_ayaka_mod(self, url: str) -> None:
        try:
            game = self.service.ayaka.game_for(url)
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)
            return
        self.call_from_thread(self._fetch_into, game, url)

    def _ayaka_login_command(self, args: tuple[str, ...]) -> None:
        if args:
            self.save_ayaka_login(one_argument(args, ":ayaka-login [xf_user]"))
            return
        self.service.ayaka.open_login()
        reason = "save or renew it"
        prompt = LoginCookiePrompt(reason, self.service.ayaka.clipboard_cookie)
        self.push_screen(
            prompt, lambda cookie: cookie and self._save_login_safely(cookie)
        )

    def _save_login_safely(self, cookie: str) -> None:
        try:
            self.save_ayaka_login(cookie)
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)

    def save_ayaka_login(self, cookie: str) -> None:
        """Store the AyakaMods cookie; e.g. ``app.save_ayaka_login('1%2Cab')``."""
        self.service.ayaka.save_login(cookie)
        self.notify(
            "Saved your AyakaMods login; its files now download directly. "
            "Logging out of AyakaMods in the browser ends it."
        )

    def action_prompt_api_key(self) -> None:
        prompt = TextPrompt(
            "Paste your personal Nexus API key "
            "(nexusmods.com/users/myaccount?tab=api)",
            "API key",
            secret=True,
        )
        self.push_screen(prompt, lambda key: key and self._save_key_safely(key))

    def _save_key_safely(self, api_key: str) -> None:
        try:
            self.save_api_key(api_key)
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)

    def save_api_key(self, api_key: str) -> None:
        """Store the key and refresh the home screen; e.g. ``app.save_api_key(k)``."""
        self.service.save_api_key(api_key)
        self.notify("API key saved to your private config.")
        for screen in self.screen_stack:
            if isinstance(screen, GamesScreen):
                screen.refresh_status()

    def action_register_nxm(self) -> None:
        try:
            registration = self.service.register_nxm()
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=10)
            return
        previous = registration.previous_handler or "none"
        self.notify(
            f"nxm links now open OmaMods (previous handler: {previous}).", timeout=10
        )
