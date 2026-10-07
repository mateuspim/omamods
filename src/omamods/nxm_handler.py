"""Receive the site's 'Mod Manager Download' clicks and stage those files."""

from dataclasses import dataclass
import json
from pathlib import Path
import time

from omamods.host_programs import CommandRunner
from omamods.mod_fetch import stage_nxm_link
from omamods.mod_plan import STALE_CATEGORIES
from omamods.nexus_api import NexusApi, parse_nxm_link

DESKTOP_ENTRY_NAME = "omamods-nxm.desktop"
NXM_MIME_TYPE = "x-scheme-handler/nxm"
UNSAFE_EXEC_CHARACTERS = frozenset('"`$\\%\n')


@dataclass(frozen=True)
class NxmRegistration:
    """Where the handler was written and what it replaced."""

    desktop_file: Path
    previous_handler: str


def desktop_entry(executable: Path) -> str:
    """Render the URL handler; e.g. ``desktop_entry(Path('/usr/bin/omamods'))``."""
    text = str(executable)
    if not executable.is_absolute() or UNSAFE_EXEC_CHARACTERS & set(text):
        raise ValueError(
            f"executable={text!r}: expected an absolute path without quotes, $, %, or \\"
        )
    # xdg-open's generic (e.g. Hyprland) mode keeps quotes as part of the
    # program name, so quote only when the desktop spec requires it.
    exec_path = f'"{text}"' if " " in text else text
    return (
        "[Desktop Entry]\nType=Application\nName=OmaMods NXM handler\n"
        f"NoDisplay=true\nExec={exec_path} nxm handle %u\n"
        f"MimeType={NXM_MIME_TYPE};\n"
    )


def register_nxm_handler(
    executable: Path, applications: Path, runner: CommandRunner
) -> NxmRegistration:
    """Make browsers hand nxm links to OmaMods; e.g. ``register_nxm_handler(exe, apps, runner)``."""
    _, previous = runner.run(("xdg-mime", "query", "default", NXM_MIME_TYPE))
    applications.mkdir(parents=True, exist_ok=True)
    desktop_file = applications / DESKTOP_ENTRY_NAME
    desktop_file.write_text(desktop_entry(executable), encoding="utf-8")
    code, _ = runner.run(("xdg-mime", "default", DESKTOP_ENTRY_NAME, NXM_MIME_TYPE))
    if code:
        raise ValueError(f"xdg-mime exit={code}: expected 0 when registering nxm")
    # The portal "Open With" chooser reads this cache; without a refresh it can
    # report "No Apps available" for nxm links until the next login.
    runner.run(("update-desktop-database", str(applications)))
    return NxmRegistration(desktop_file, previous)


def log_nxm_event(log: Path, event: dict[str, object]) -> None:
    """Append one JSON line; e.g. ``log_nxm_event(path, {'status': 'staged'})``."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": int(time.time()), **event}) + "\n")


def handle_nxm_click(
    link_text: str, api: NexusApi, root: Path, runner: CommandRunner
) -> int:
    """Stage a clicked file; e.g. ``handle_nxm_click('nxm://...', api, root, runner)``."""
    log = root / "logs/nxm.jsonl"
    try:
        clicked = stage_nxm_link(api, root, parse_nxm_link(link_text))
    except Exception as error:  # Browser-launched: no terminal shows a traceback.
        log_nxm_event(log, {"status": "failed", "error": repr(error)})
        runner.run(("notify-send", "OmaMods download failed", str(error)))
        return 1
    event = {
        "status": "staged",
        "game": clicked.game.game_id,
        "file": clicked.describe(),
    }
    log_nxm_event(log, {**event, "archive": str(clicked.archive)})
    title = f"OmaMods staged {clicked.game.name} mod"
    if clicked.file.category in STALE_CATEGORIES:
        title = f"OmaMods staged an OLD {clicked.game.name} file - check it"
    runner.run(("notify-send", title, clicked.describe()))
    return 0
