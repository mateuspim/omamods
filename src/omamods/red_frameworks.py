"""Spot Cyberpunk 2077 frameworks on disk and the Proton setup they need."""

from collections.abc import Callable
from pathlib import Path
import re

RED4EXT_MOD_ID = 2380
CET_MOD_ID = 107
# A file or folder each framework puts in the game folder, so one installed by
# hand or by another manager counts as present and is not installed twice.
RED_FRAMEWORK_MARKERS: dict[int, str] = {
    RED4EXT_MOD_ID: "red4ext/RED4ext.dll",
    4198: "red4ext/plugins/ArchiveXL",
    4197: "red4ext/plugins/TweakXL",
    7780: "red4ext/plugins/Codeware",
    1511: "engine/tools/scc.exe",
    CET_MOD_ID: "bin/x64/plugins/cyber_engine_tweaks.asi",
    3518: "bin/x64/plugins/cyber_engine_tweaks/mods/nativeSettings",
}
# RED4ext loads through winmm.dll and CET through version.dll; Wine prefers its
# builtin copies unless the launch options override them.
RED_PROXY_DLLS: dict[int, str] = {RED4EXT_MOD_ID: "winmm", CET_MOD_ID: "version"}
# Which loader each proxy DLL belongs to, to name it in the hint.
PROXY_LOADERS: dict[str, str] = {
    "winmm": "RED4ext",
    "version": "CET",
    "dwmapi": "UE4SS",
    "xinput1_3": "UE4SS",
}
OVERRIDES_PATTERN = re.compile(r"WINEDLLOVERRIDES=(?:\"([^\"]*)\"|'([^']*)'|(\S+))")
PathProbe = Callable[[Path], bool]


def frameworks_on_disk(game_root: Path, exists: PathProbe) -> frozenset[int]:
    """Report present framework mod IDs; e.g. ``frameworks_on_disk(root, Path.exists)``."""
    return frozenset(
        mod_id
        for mod_id, marker in RED_FRAMEWORK_MARKERS.items()
        if exists(game_root / marker)
    )


def native_overrides(launch_options: str) -> frozenset[str]:
    """DLLs Wine loads natively; e.g. ``native_overrides('WINEDLLOVERRIDES="winmm=n,b" %command%')``."""
    found: set[str] = set()
    for match in OVERRIDES_PATTERN.finditer(launch_options):
        value = next(group for group in match.groups() if group is not None)
        for entry in value.split(";"):
            dlls, _, mode = entry.partition("=")
            if mode.strip().lower().startswith("n"):
                found.update(d.strip().lower() for d in dlls.split(",") if d.strip())
    return frozenset(found)


def missing_proxy_dlls(
    framework_ids: frozenset[int],
    launch_options: tuple[str, ...],
    loader_dlls: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """DLL overrides still needed; e.g. ``missing_proxy_dlls(frozenset({2380}), opts)``.

    ``loader_dlls`` adds proxies found on disk, such as UE4SS' ``dwmapi``.
    """
    needed = {RED_PROXY_DLLS[i] for i in framework_ids if i in RED_PROXY_DLLS}
    needed |= loader_dlls
    for options in launch_options:
        needed -= native_overrides(options)
    return tuple(sorted(needed))


def launch_options_hint(missing: tuple[str, ...], loader: str | None = None) -> str:
    """Tell people what to set; e.g. ``launch_options_hint(('version', 'winmm'))``.

    ``loader`` names the mod loader when the DLL alone is ambiguous: winmm.dll
    is RED4ext in Cyberpunk but the ASI loader in MGSV.
    """
    dlls = ",".join(missing)
    loaders = [loader] if loader else sorted({PROXY_LOADERS.get(d, d) for d in missing})
    return (
        f'Add WINEDLLOVERRIDES="{dlls}=n,b" before %command% in the game\'s '
        f"Steam launch options so Proton loads "
        f"{' and '.join(f'{dll}.dll' for dll in missing)}; without it "
        f"{' and '.join(loaders)} mods do nothing."
    )
