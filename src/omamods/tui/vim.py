"""Map vim motions onto whichever list or table has focus."""

from textual.widget import Widget

# Each motion names the widget actions to try, in order (OptionList, DataTable).
MOTION_ACTIONS: dict[str, tuple[str, ...]] = {
    "down": ("cursor_down",),
    "up": ("cursor_up",),
    "top": ("first", "scroll_top"),
    "bottom": ("last", "scroll_bottom"),
    "page_down": ("page_down",),
    "page_up": ("page_up",),
}
GG_SECONDS = 0.6


def run_motion(widget: Widget | None, motion: str) -> bool:
    """Apply a motion to the focused widget; e.g. ``run_motion(app.focused, 'down')``."""
    for name in MOTION_ACTIONS[motion]:
        action = getattr(widget, f"action_{name}", None)
        if callable(action):
            action()
            return True
    return False


class ChordTracker:
    """Recognise 'gg' as two presses within ``GG_SECONDS``; e.g. ``tracker.press(now)``."""

    def __init__(self) -> None:
        self.last: float | None = None

    def press(self, now: float) -> bool:
        """Record a 'g'; True when it completes 'gg'. E.g. ``tracker.press(1.0)``."""
        completed = self.last is not None and now - self.last <= GG_SECONDS
        self.last = None if completed else now
        return completed
