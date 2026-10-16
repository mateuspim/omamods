"""Keep one error toast on screen when the same failure repeats.

Pressing i three times on a refused MGS Delta archive stacked the same
"loaders and scripts" error three times; the first toast already says it all.
"""

from collections.abc import Callable
import time

Clock = Callable[[], float]


class RepeatedToastFilter:
    """Remember shown messages until their toast would have timed out."""

    def __init__(self, seconds: float, clock: Clock = time.monotonic) -> None:
        self.seconds = seconds
        self.clock = clock
        self.shown_until: dict[str, float] = {}

    def should_show(self, message: str) -> bool:
        """Allow a toast once per timeout; e.g. ``toasts.should_show(str(error))``."""
        now = self.clock()
        if self.shown_until.get(message, 0.0) > now:
            return False
        self.shown_until = {
            text: until for text, until in self.shown_until.items() if until > now
        }
        self.shown_until[message] = now + self.seconds
        return True
