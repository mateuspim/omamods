"""':' commands for one game's mods screen, e.g. ``:install Hair``."""

from collections.abc import Callable
from typing import TYPE_CHECKING

from omamods.mod_plan import preselected_download
from omamods.nexus_api import NexusFile
from omamods.staging import StagedMod
from omamods.tui.commands import CommandSpec, find_file

if TYPE_CHECKING:
    from omamods.tui.mods_screen import ModsScreen

MODS_COMMANDS = (
    CommandSpec("install", ("i",), ":install [file]", "install the mod, or one file"),
    CommandSpec(
        "uninstall", ("u",), ":uninstall [file]", "uninstall the mod, or one file"
    ),
    CommandSpec(
        "download",
        ("d",),
        ":download [file|all]",
        "download selected, one, or all files",
    ),
    CommandSpec("rm", ("x",), ":rm <file>", "delete a download from staging"),
    CommandSpec("web", ("w",), ":web", "open the mod's Nexus page"),
    CommandSpec("picture", ("o",), ":picture", "open the full picture in imv"),
    CommandSpec(
        "dl", (), ":dl [min|game|full]", "resize the downloads panel (D cycles)"
    ),
)
PANEL_SIZES = {"min": "minimized", "game": "game", "full": "full"}
# Files are given by the ID column or a unique part of their name.


def _current_mod(screen: "ModsScreen") -> StagedMod:
    if screen.current is None:
        raise ValueError("mod: expected one selected; add one with :add <url>")
    return screen.current


def _named_file(screen: "ModsScreen", args: tuple[str, ...]) -> NexusFile:
    return find_file(_current_mod(screen).files, " ".join(args))


def _install(screen: "ModsScreen", args: tuple[str, ...]) -> None:
    if not args:
        screen.action_install_mod()
        return
    mod, file = _current_mod(screen), _named_file(screen, args)
    if file.file_id not in mod.archives:
        raise ValueError(
            f"file={file.file_name!r}: expected it downloaded; :download it"
        )
    screen.install_files(mod, (file,))


def _uninstall(screen: "ModsScreen", args: tuple[str, ...]) -> None:
    if not args:
        screen.action_uninstall_mod()
        return
    mod, file = _current_mod(screen), _named_file(screen, args)
    if file.file_id not in mod.installed:
        raise ValueError(f"file={file.file_name!r}: expected an installed file")
    screen.confirm_uninstall(mod, (file,))


def _download(screen: "ModsScreen", args: tuple[str, ...]) -> None:
    if not args:
        screen.action_download()
        return
    mod = _current_mod(screen)
    if args == ("all",):
        files = tuple(
            f
            for f in mod.files
            if preselected_download(f) and f.file_id not in mod.archives
        )
        if not files:
            raise ValueError(
                f"{mod.title}: expected files left to download; all staged"
            )
    else:
        files = (_named_file(screen, args),)
    screen.download_files(mod.mod_id, files)


def _remove(screen: "ModsScreen", args: tuple[str, ...]) -> None:
    if not args:
        raise ValueError(":rm <file>: expected a file ID or name")
    screen.confirm_remove(_named_file(screen, args))


def _resize_downloads(screen: "ModsScreen", args: tuple[str, ...]) -> None:
    if not args:
        screen.action_cycle_downloads()
        return
    size = PANEL_SIZES.get(" ".join(args).lower())
    if size is None:
        raise ValueError(f":dl size={' '.join(args)!r}: expected min, game, or full")
    screen.show_downloads(size)


HANDLERS: dict[str, Callable[["ModsScreen", tuple[str, ...]], None]] = {
    "install": _install,
    "uninstall": _uninstall,
    "download": _download,
    "rm": _remove,
    "web": lambda screen, args: screen.action_open_page(),
    "picture": lambda screen, args: screen.action_open_picture(),
    "dl": _resize_downloads,
}


def run_mods_command(screen: "ModsScreen", name: str, args: tuple[str, ...]) -> None:
    """Dispatch a resolved command; e.g. ``run_mods_command(screen, 'rm', ('1028',))``."""
    HANDLERS[name](screen, args)
