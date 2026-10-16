"""':' commands for one game's mods screen, e.g. ``:install Hair``."""

from collections.abc import Callable
from typing import TYPE_CHECKING

from omamods.mod_plan import preselected_download
from omamods.nexus_api import NexusFile
from omamods.mod_sites import AYAKA_SITE
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
    CommandSpec("web", ("w",), ":web", "open the mod's web page"),
    CommandSpec("picture", ("o",), ":picture", "open the full picture in imv"),
    CommandSpec("preview", ("p",), ":preview", "toggle the artwork split"),
    CommandSpec(
        "dl", (), ":dl [min|game|full]", "resize the downloads panel (D cycles)"
    ),
    CommandSpec("stop", (), ":stop", "stop waiting for an AyakaMods download"),
    CommandSpec(
        "nsfw",
        (),
        ":nsfw [blur|hide|show|mark|unmark]",
        "blur, hide, or show NSFW mods (H), or mark this mod (m)",
    ),
)
PANEL_SIZES = {"min": "minimized", "game": "game", "full": "full"}
NSFW_CHOICES = ("blur", "hide", "show", "mark", "unmark")
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
    if mod.site == AYAKA_SITE:
        # The site lists the files (or the browser does, without a login).
        screen.download_ayaka(mod)
        return
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


def _nsfw(screen: "ModsScreen", args: tuple[str, ...]) -> None:
    choice = " ".join(args).lower()
    if not choice:
        screen.action_cycle_adult()
    elif choice in ("blur", "hide", "show"):
        screen.set_adult_mode(choice)
    elif choice in ("mark", "unmark"):
        screen.mark_adult(choice == "mark")
    else:
        raise ValueError(f":nsfw choice={choice!r}: expected one of {NSFW_CHOICES}")


HANDLERS: dict[str, Callable[["ModsScreen", tuple[str, ...]], None]] = {
    "install": _install,
    "uninstall": _uninstall,
    "download": _download,
    "rm": _remove,
    "web": lambda screen, args: screen.action_open_page(),
    "picture": lambda screen, args: screen.action_open_picture(),
    "preview": lambda screen, args: screen.action_toggle_preview(),
    "dl": _resize_downloads,
    "stop": lambda screen, args: screen.cancel_ayaka(),
    "nsfw": _nsfw,
}


def run_mods_command(screen: "ModsScreen", name: str, args: tuple[str, ...]) -> None:
    """Dispatch a resolved command; e.g. ``run_mods_command(screen, 'rm', ('1028',))``."""
    HANDLERS[name](screen, args)
