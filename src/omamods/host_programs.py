"""Run or launch host programs (xdg-mime, notify-send, imv, xdg-open)."""

import subprocess
from typing import Protocol


class CommandRunner(Protocol):
    """Run host commands such as xdg-mime and notify-send."""

    def run(self, command: tuple[str, ...]) -> tuple[int, str]:
        """Return exit code and stdout; e.g. ``runner.run(('xdg-mime', 'query'))``."""
        ...


class SubprocessRunner:
    """Run commands on the host; a missing program counts as exit code 127."""

    def run(self, command: tuple[str, ...]) -> tuple[int, str]:
        """Run without a shell; e.g. ``SubprocessRunner().run(('true',))``."""
        try:
            result = subprocess.run(command, capture_output=True, text=True)
        except FileNotFoundError:
            return 127, ""
        return result.returncode, result.stdout.strip()


class Launcher(Protocol):
    """Start a GUI program without waiting, e.g. imv or a browser."""

    def launch(self, command: tuple[str, ...]) -> None:
        """Start detached; for example, ``launcher.launch(('imv', path))``."""
        ...


class DetachedLauncher:
    """Start programs in their own session so closing the TUI keeps them open."""

    def launch(self, command: tuple[str, ...]) -> None:
        """Start detached; for example, ``DetachedLauncher().launch(('imv', p))``."""
        try:
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError as error:
            raise ValueError(f"program={command[0]!r}: expected it on PATH") from error
