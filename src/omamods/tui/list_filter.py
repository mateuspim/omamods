"""Match list rows against a '/' query and mark the matching letters."""

from rich.text import Text

MATCH_STYLE = "bold reverse"


def query_words(query: str) -> tuple[str, ...]:
    """Split a query into lowercase words; e.g. ``query_words('Blue  SUIT')``."""
    # lower(), not casefold(): casefold turns ß into ss and shifts mark offsets.
    return tuple(query.lower().split())


def matches_query(name: str, query: str) -> bool:
    """True when every query word appears in name; e.g. ``matches_query('Hair Pack', 'pa ha')``."""
    folded = name.lower()
    return all(word in folded for word in query_words(query))


def mark_matches(name: str, query: str) -> Text:
    """Style each query word inside name; e.g. ``Option(mark_matches(title, 'hair'))``."""
    text = Text(name)
    folded = name.lower()
    for word in query_words(query):
        start = folded.find(word)
        while start != -1:
            text.stylize(MATCH_STYLE, start, start + len(word))
            start = folded.find(word, start + len(word))
    return text


def search_title(title: str, query: str, shown: int, total: int) -> str:
    """Name a panel and its active filter; e.g. ``search_title('Mods', 'hair', 2, 9)``."""
    if not query:
        return title
    return f"{title} · /{query} ({shown}/{total})"
