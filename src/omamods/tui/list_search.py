"""Vim-style '/' for a screen's main list: filter as you type, n/N cycle, Esc clears."""

from textual.screen import Screen
from textual.widgets import OptionList


class SearchableScreen(Screen[None]):
    """Base for screens whose list '/' filters; e.g. ``class S(SearchableScreen)``.

    Subclasses rebuild their list from ``search_query`` in ``rebuild_list``.
    """

    SEARCH_LIST_ID = ""

    def __init__(self) -> None:
        super().__init__()
        self.search_query = ""

    def rebuild_list(self, jump_to_first: bool) -> int:
        """Re-list the rows matching ``search_query``; return how many are shown."""
        raise NotImplementedError(f"{type(self).__name__} must define rebuild_list")

    def filter_list(self, query: str) -> int:
        """Show only rows matching query; e.g. ``screen.filter_list('hair') == 2``."""
        self.search_query = query
        # A new query lands on its first match; clearing it keeps the row you found.
        return self.rebuild_list(jump_to_first=bool(query))

    def search(self, text: str) -> None:
        """Keep rows matching text, like vim's '/'; e.g. ``screen.search('blade')``."""
        if self.filter_list(text) == 0 and text:
            self.notify(f"E486: Pattern not found: {text}", severity="warning")
            self.filter_list("")

    def action_clear_search(self) -> None:
        """Show every row again, staying on the highlighted one."""
        self.filter_list("")

    def action_next_match(self, step: int) -> None:
        """Move to the next (1) or previous (-1) match, wrapping like vim's n/N."""
        if not self.search_query:
            self.notify("E35: No previous regular expression; press / to search")
            return
        rows = self.query_one(f"#{self.SEARCH_LIST_ID}", OptionList)
        count = rows.option_count
        enabled = [i for i in range(count) if not rows.get_option_at_index(i).disabled]
        if enabled:
            rows.highlighted = wrapped_step(enabled, rows.highlighted, step)


def wrapped_step(enabled: list[int], current: int | None, step: int) -> int:
    """Pick the next enabled row after current, wrapping; e.g. ``wrapped_step([1, 3], 3, 1) == 1``."""
    ahead = [i for i in enabled if current is None or (i - current) * step > 0]
    if not ahead:
        return enabled[0] if step > 0 else enabled[-1]
    return min(ahead) if step > 0 else max(ahead)
