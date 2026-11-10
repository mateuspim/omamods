"""Suggest display resolutions for patches that need one, monitors first.

Hyprland reports each monitor's mode in physical pixels (`hyprctl monitors
-j`), which is what a game renders at regardless of desktop scaling. Other
desktops give no answer, so the list falls back to common sizes. Sizes
narrower than 16:9 are listed but not selectable, with the reason.
"""

from dataclasses import dataclass
import json
import math

from omamods.host_programs import CommandRunner

COMMON_SIZES: tuple[tuple[int, int], ...] = (
    (2560, 1080),
    (3440, 1440),
    (3840, 1600),
    (5120, 2160),
    (3840, 1080),
    (5120, 1440),
    (1920, 1080),
    (2560, 1440),
    (3840, 2160),
)
# Marketing names for ratios; 21:9 covers 64:27 (2560x1080) and 43:18 (3440x1440).
ASPECT_NAMES: tuple[tuple[float, str], ...] = (
    (4 / 3, "4:3"),
    (5 / 4, "5:4"),
    (16 / 10, "16:10"),
    (16 / 9, "16:9"),
    (21 / 9, "21:9"),
    (32 / 9, "32:9"),
)
NARROW_REASON = "needs 16:9 or wider"


@dataclass(frozen=True)
class Monitor:
    """One connected display and its current mode."""

    name: str
    model: str
    width: int
    height: int
    focused: bool


@dataclass(frozen=True)
class SizeChoice:
    """One row of a resolution picker."""

    size: str
    label: str
    allowed: bool


def _monitor(fields: object) -> Monitor | None:
    if not isinstance(fields, dict):
        return None
    width, height = fields.get("width"), fields.get("height")
    if not (isinstance(width, int) and isinstance(height, int) and width and height):
        return None
    name, model = str(fields.get("name", "")), str(fields.get("model", "")).strip()
    return Monitor(name, model, width, height, fields.get("focused") is True)


def read_monitors(runner: CommandRunner) -> tuple[Monitor, ...]:
    """Ask Hyprland for monitors, focused first; e.g. ``read_monitors(runner)``."""
    code, output = runner.run(("hyprctl", "monitors", "-j"))
    if code != 0:
        return ()
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return ()
    found = [m for m in map(_monitor, parsed if isinstance(parsed, list) else []) if m]
    return tuple(sorted(found, key=lambda monitor: not monitor.focused))


def aspect_name(width: int, height: int) -> str:
    """Name a ratio; e.g. ``aspect_name(3440, 1440) == '21:9'``."""
    ratio = width / height
    for value, name in ASPECT_NAMES:
        if abs(ratio - value) / value < 0.04:
            return name
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def _choice(width: int, height: int, where: str) -> SizeChoice:
    allowed = width * 9 >= height * 16
    note = where if allowed else f"{where}  {NARROW_REASON}".strip()
    label = f"{width}x{height}".ljust(11) + aspect_name(width, height).ljust(7) + note
    return SizeChoice(f"{width}x{height}", label.rstrip(), allowed)


def _where(monitor: Monitor) -> str:
    model = f" · {monitor.model}" if monitor.model else ""
    focused = "  (focused)" if monitor.focused else ""
    return f"{monitor.name}{model}{focused}"


def resolution_choices(monitors: tuple[Monitor, ...]) -> tuple[SizeChoice, ...]:
    """Monitors first, then common wide sizes; e.g. ``resolution_choices(mine)``."""
    rows: dict[str, SizeChoice] = {}
    for monitor in monitors:
        choice = _choice(monitor.width, monitor.height, _where(monitor))
        rows.setdefault(choice.size, choice)
    for width, height in COMMON_SIZES:
        rows.setdefault(f"{width}x{height}", _choice(width, height, ""))
    return tuple(rows.values())
