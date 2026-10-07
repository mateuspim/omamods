"""Open Nexus pages in their own browser window; hide it once a download starts
and close it after downloads.

Chromium-family browsers started with ``--app=<url>`` get a Hyprland window
class derived from the URL, e.g.
``brave-www.nexusmods.com__stellarblade_mods_1-Default``. That lets OmaMods
close exactly the window it opened without touching the user's other tabs.
"""

import json
from pathlib import Path
import re
import shlex

from omamods.host_programs import CommandRunner, Launcher

CHROMIUM_NAMES = ("brave", "chrom", "vivaldi", "edge", "opera")
HYPRLAND_ADDRESS = re.compile(r"0x[0-9a-f]+")
# Where started downloads park their window; `hyprctl dispatch togglespecialworkspace omamods` shows it.
HIDDEN_WORKSPACE = "special:omamods"


def exec_program(desktop_entry: str) -> str | None:
    """Read a launcher's program; e.g. ``exec_program('Exec=/bin/brave %U')``."""
    for line in desktop_entry.splitlines():
        if line.startswith("Exec="):
            words = shlex.split(line.removeprefix("Exec="))
            return words[0] if words else None
    return None


def chromium_browser(runner: CommandRunner, data_dirs: tuple[Path, ...]) -> str | None:
    """Find a default browser that supports ``--app``; e.g. ``chromium_browser(r, dirs)``."""
    code, desktop_id = runner.run(("xdg-settings", "get", "default-web-browser"))
    if code or not desktop_id.endswith(".desktop"):
        return None
    for folder in data_dirs:
        entry = folder / "applications" / desktop_id
        if not entry.is_file():
            continue
        program = exec_program(entry.read_text(encoding="utf-8", errors="replace"))
        name = Path(program).name.lower() if program else ""
        return program if any(part in name for part in CHROMIUM_NAMES) else None
    return None


def nexus_window_class(domain: str, mod_id: int) -> re.Pattern[str]:
    """Match a mod's app window class; e.g. ``nexus_window_class('stellarblade', 1)``."""
    # The trailing (-|$) keeps mod 1 from matching mod 12's window.
    return re.compile(rf"www\.nexusmods\.com__{re.escape(domain)}_mods_{mod_id}(-|$)")


class NexusWindows:
    """Open and close per-mod Nexus windows; e.g. ``NexusWindows(r, l, 'brave')``."""

    def __init__(
        self, runner: CommandRunner, launcher: Launcher, browser: str | None
    ) -> None:
        self.runner = runner
        self.launcher = launcher
        self.browser = browser

    def open(self, url: str) -> bool:
        """Open ``url``; True when it can be closed later. E.g. ``windows.open(u)``."""
        if self.browser is None:
            self.launcher.launch(("xdg-open", url))
            return False
        self.launcher.launch((self.browser, f"--app={url}"))
        return True

    def _addresses(self, domain: str, mod_id: int) -> tuple[str, ...]:
        code, output = self.runner.run(("hyprctl", "clients", "-j"))
        try:
            clients = json.loads(output) if code == 0 else []
        except ValueError:
            return ()
        pattern = nexus_window_class(domain, mod_id)
        return tuple(
            str(client["address"])
            for client in clients
            if isinstance(client, dict)
            and pattern.search(str(client.get("initialClass", "")))
            and HYPRLAND_ADDRESS.fullmatch(str(client.get("address", "")))
        )

    def _dispatch(self, lua: str, legacy: tuple[str, ...]) -> None:
        # Lua-config Hyprland (seen on 0.56.2) needs the Lua form; older takes legacy.
        _, output = self.runner.run(("hyprctl", "dispatch", lua))
        if output != "ok":
            self.runner.run(("hyprctl", "dispatch", *legacy))

    def _close(self, address: str) -> None:
        lua = f'hl.dsp.window.close({{ window = "address:{address}" }})'
        self._dispatch(lua, ("closewindow", f"address:{address}"))

    def _hide(self, address: str) -> None:
        # Hyprland has no minimise; Omarchy's scratchpad uses this same silent move.
        lua = (
            f'hl.dsp.window.move({{ workspace = "{HIDDEN_WORKSPACE}", '
            f'follow = false, window = "address:{address}" }})'
        )
        legacy = f"{HIDDEN_WORKSPACE},address:{address}"
        self._dispatch(lua, ("movetoworkspacesilent", legacy))

    def close_mod(self, domain: str, mod_id: int) -> int:
        """Close a mod's windows; e.g. ``windows.close_mod('stellarblade', 1)``."""
        addresses = self._addresses(domain, mod_id)
        for address in addresses:
            self._close(address)
        return len(addresses)

    def hide_mod(self, domain: str, mod_id: int) -> int:
        """Move a mod's windows off screen; e.g. ``windows.hide_mod('stellarblade', 1)``."""
        addresses = self._addresses(domain, mod_id)
        for address in addresses:
            self._hide(address)
        return len(addresses)
