"""Pick the hint-line keys that do something for what the cursor is on.

The bottom line used to be one fixed string per screen, so it named keys that
did nothing for the selected mod (x on a file never downloaded) and missed
ones that did (u on an installed mod). These functions look at the mod and
file under the cursor and list only the keys that would act on them.
"""

from collections.abc import Callable

from textual.widget import Widget
from textual.widgets import OptionList

from omamods.mod_sites import AYAKA_SITE, NEXUS_SITE, PATCH_SITE
from omamods.nexus_api import NexusFile
from omamods.staging import StagedMod
from omamods.tui.mod_rows import file_next_action

KeyHint = tuple[str, str]
# Sites whose mods x can drop from the list once nothing is downloaded.
LISTED_SITES = (NEXUS_SITE, AYAKA_SITE)


def key_hints(*pairs: KeyHint) -> str:
    """Format keys for the hint line; e.g. ``key_hints(('i', 'install'))``."""
    return "   ".join(f"[b]{key}[/] {label}" for key, label in pairs)


def patch_pairs(mod: StagedMod) -> tuple[KeyHint, ...]:
    """Keys for a built-in exe patch; e.g. ``patch_pairs(mgr_patch)``."""
    if mod.installed:
        return (("u", "restore original"), ("x", "restore + remove patch"))
    return (("i", "patch exe"), ("x", "remove from list"))


def file_pairs(mod: StagedMod, file: NexusFile) -> tuple[KeyHint, ...]:
    """Keys for one file of a mod; e.g. ``file_pairs(staged, staged.files[0])``."""
    if mod.site == PATCH_SITE:
        action = "restore" if file.file_id in mod.installed else "patch"
        return (("enter", action),) + patch_pairs(mod)[1:]
    pairs: list[KeyHint] = [("enter", file_next_action(mod, file))]
    if file.file_id in mod.archives:
        pairs.append(("x", "remove download"))
    elif file.file_id not in mod.installed:
        pairs.append(("d", "download"))
    if not mod.archives and not mod.installed and mod.site in LISTED_SITES:
        pairs.append(("x", "remove mod"))
    if file.file_id in mod.installed:
        pairs.append(("P", "load last"))
    return tuple(pairs)


def _mod_actions(mod: StagedMod) -> list[KeyHint]:
    pairs: list[KeyHint] = []
    if set(mod.archives) - mod.installed:
        pairs.append(("i", "install"))
    if mod.installed:
        pairs.append(("u", "uninstall"))
    if mod.picture is not None:
        pairs.append(("o", "picture"))
    return pairs


def mod_list_pairs(
    mod: StagedMod | None, file: NexusFile | None
) -> tuple[KeyHint, ...]:
    """Keys for the highlighted mod; e.g. ``mod_list_pairs(staged, file)``."""
    if mod is None:
        return (("a", "add mod"), ("/", "find"))
    if mod.site == PATCH_SITE:
        return patch_pairs(mod) + (("w", "about"),)
    pairs = _mod_actions(mod)
    if file is not None:
        pairs += [pair for pair in file_pairs(mod, file) if pair[0] in "dx"]
    return (*pairs, ("enter", "files"), ("w", "web page"), ("a", "add"), ("/", "find"))


class ModListHints:
    """Mixin giving the hint line the mod list's keys; see ``context_hints``."""

    # Annotations only, so ModsScreen's own methods are used.
    current: StagedMod | None
    _selected_file: Callable[[], NexusFile | None]

    def context_hints(self, focused: Widget | None) -> str | None:
        """Hints while the mod list has focus; e.g. ``screen.context_hints(w)``."""
        if not isinstance(focused, OptionList) or focused.id != "mods":
            return None
        return key_hints(*mod_list_pairs(self.current, self._selected_file()))
