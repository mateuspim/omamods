"""Work out the exact Steam launch options line a person should paste.

Steam keeps one free-text field per game, often already holding other
settings (PROTON_ENABLE_HDR=1 ... %command%), so the fix must merge into it
rather than replace it.
"""

from dataclasses import dataclass

from omamods.proton_runtime import FileVersion, is_outdated_runtime, vcrun_command
from omamods.red_frameworks import (
    OVERRIDES_PATTERN,
    RED_PROXY_DLLS,
    missing_proxy_dlls,
)

COMMAND = "%command%"


@dataclass(frozen=True)
class LaunchOptionsAdvice:
    """What Steam has, which DLLs lack an override, and what to paste."""

    current: str
    missing: tuple[str, ...]
    suggested: str
    # The prefix's msvcp140 version, and the protontricks command to run when
    # it is too old for RED4ext/CET (error 998); None when it is fine.
    runtime: FileVersion | None = None
    runtime_fix: str | None = None

    @property
    def needed(self) -> bool:
        """True when Steam or the prefix must change; e.g. ``advice.needed``."""
        return bool(self.missing) or self.runtime_fix is not None


def _override(missing: tuple[str, ...]) -> str:
    return f"{','.join(missing)}=n,b"


def merged_launch_options(current: str, missing: tuple[str, ...]) -> str:
    """Add overrides, keeping the rest; e.g. ``merged_launch_options('%command%', ('winmm',))``."""
    if not missing:
        return current
    match = OVERRIDES_PATTERN.search(current)
    if match is not None:
        existing = next(group for group in match.groups() if group is not None)
        value = f'WINEDLLOVERRIDES="{existing};{_override(missing)}"'
        return current[: match.start()] + value + current[match.end() :]
    prefix = f'WINEDLLOVERRIDES="{_override(missing)}"'
    if COMMAND in current:
        return f"{prefix} {current.strip()}"
    # Without %command%, Steam passes the text to the game as arguments.
    return f"{prefix} {COMMAND} {current.strip()}".rstrip()


def launch_options_advice(
    options: tuple[str, ...],
    framework_ids: frozenset[int],
    runtime: FileVersion | None = None,
    app_id: str | None = None,
) -> LaunchOptionsAdvice:
    """Advise on the first Steam user's line; e.g. ``launch_options_advice(opts, ids)``."""
    current = options[0] if options else ""
    missing = missing_proxy_dlls(framework_ids, (current,))
    suggested = merged_launch_options(current, missing)
    fix = _runtime_fix(framework_ids, runtime, app_id)
    return LaunchOptionsAdvice(current, missing, suggested, runtime, fix)


def _runtime_fix(
    framework_ids: frozenset[int], runtime: FileVersion | None, app_id: str | None
) -> str | None:
    # Only the DLL loaders (RED4ext, CET) fault on an old runtime.
    loaders = framework_ids & frozenset(RED_PROXY_DLLS)
    if app_id is None or not loaders or not is_outdated_runtime(runtime):
        return None
    return vcrun_command(app_id)
