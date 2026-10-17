"""Close and restart the Steam client around edits to its config files.

Steam holds localconfig.vdf in memory and writes it back on exit, so a launch
options edit made while it runs is lost. ``steam -shutdown`` asks the running
client to exit cleanly (it saves its own state first).
"""

from collections.abc import Callable
import time

from omamods.host_programs import CommandRunner, Launcher

SHUTDOWN_TIMEOUT_SECONDS = 60.0
POLL_SECONDS = 0.5


class SteamProcess:
    """Check, stop, and start the Steam client; e.g. ``SteamProcess(runner, launcher)``."""

    def __init__(
        self,
        runner: CommandRunner,
        launcher: Launcher,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = SHUTDOWN_TIMEOUT_SECONDS,
    ) -> None:
        self.runner = runner
        self.launcher = launcher
        self.sleep = sleep
        self.timeout = timeout

    def running(self) -> bool:
        """Report a running client; e.g. ``steam.running()``."""
        code, _ = self.runner.run(("pgrep", "-x", "steam"))
        return code == 0

    def shut_down(self) -> None:
        """Ask Steam to exit and wait until it has; e.g. ``steam.shut_down()``."""
        self.launcher.launch(("steam", "-shutdown"))
        waited = 0.0
        while self.running():
            if waited >= self.timeout:
                raise ValueError(
                    f"Steam still running after {waited:.0f}s: expected it to exit; "
                    "close it from its tray menu and try again"
                )
            self.sleep(POLL_SECONDS)
            waited += POLL_SECONDS

    def start(self) -> None:
        """Start Steam in the tray; e.g. ``steam.start()``."""
        self.launcher.launch(("steam", "-silent"))
