"""Work out the exact Steam launch options line a person should paste.

Steam keeps one free-text field per game, often already holding other
settings (PROTON_ENABLE_HDR=1 ... %command%), so the fix must merge into it
rather than replace it.
"""

from dataclasses import dataclass

from omamods.red_frameworks import OVERRIDES_PATTERN, missing_proxy_dlls

COMMAND = "%command%"


@dataclass(frozen=True)
class LaunchOptionsAdvice:
    """What Steam has, which DLLs lack an override, and what to paste."""

    current: str
    missing: tuple[str, ...]
    suggested: str

    @property
    def needed(self) -> bool:
        """True when Steam's line must change; e.g. ``advice.needed``."""
        return bool(self.missing)


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
    options: tuple[str, ...], framework_ids: frozenset[int]
) -> LaunchOptionsAdvice:
    """Advise on the first Steam user's line; e.g. ``launch_options_advice(opts, ids)``."""
    current = options[0] if options else ""
    missing = missing_proxy_dlls(framework_ids, (current,))
    return LaunchOptionsAdvice(
        current, missing, merged_launch_options(current, missing)
    )
