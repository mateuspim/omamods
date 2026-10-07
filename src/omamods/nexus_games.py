"""Match installed games to Nexus game domains through a cached game list."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata

from omamods.nexus_api import NexusApi

# Nexus adds games rarely; a week keeps the 3 MB list off every rescan.
CACHE_MAX_AGE_SECONDS = 7 * 24 * 3600
DOMAIN_PATTERN = re.compile(r"[a-z0-9]+")
# Nexus tells remakes apart with a year, e.g. "Silent Hill 2 (2024)".
TRAILING_QUALIFIER = re.compile(r"\s*\([^()]*\)\s*$")
# Steam bundles name their DLC, e.g. "KINGDOM HEARTS III + Re Mind (DLC)".
BUNDLE_SUFFIX = re.compile(r"\s+\+\s.*$")
# NFKD leaves Greek letters alone; Nexus spells them out (Metal Gear Solid Δ).
SPELLED_SYMBOLS = {"™": "", "®": "", "Δ": "Delta"}


def title_key(title: str) -> str:
    """Fold a title for matching; e.g. ``title_key('Stellar Blade™') == 'stellarblade'``."""
    for symbol, spelled in SPELLED_SYMBOLS.items():
        title = title.replace(symbol, spelled)
    folded = unicodedata.normalize("NFKD", title)
    return "".join(c for c in folded.casefold() if c.isalnum())


def title_keys(title: str) -> tuple[str, ...]:
    """List keys, exact first; e.g. ``title_keys('Silent Hill 2 (2024)')``."""
    trimmed = BUNDLE_SUFFIX.sub("", TRAILING_QUALIFIER.sub("", title))
    keys = (title_key(title), title_key(trimmed))
    return tuple(dict.fromkeys(key for key in keys if key))


@dataclass(frozen=True)
class NexusGameDirectory:
    """Nexus domains by folded title; e.g. ``directory.domain_for('Remnant II')``."""

    domains: dict[str, str]

    def domain_for(self, *titles: str) -> str | None:
        """Find the first title Nexus knows; e.g. ``directory.domain_for(name)``."""
        for key in (key for title in titles for key in title_keys(title)):
            domain = self.domains.get(key)
            if domain is not None:
                return domain
        return None


EMPTY_DIRECTORY = NexusGameDirectory({})


def _game_pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict):
        raise ValueError(f"Nexus game={value!r}: expected an object")
    name, domain = value.get("name"), value.get("domain_name")
    if not isinstance(name, str) or not isinstance(domain, str):
        raise ValueError(f"Nexus game={value!r}: expected name and domain_name")
    if not DOMAIN_PATTERN.fullmatch(domain):
        raise ValueError(f"Nexus domain_name={domain!r}: expected [a-z0-9]+")
    return tuple((key, domain) for key in title_keys(name))


def parse_game_directory(value: object) -> NexusGameDirectory:
    """Validate ``/v1/games.json``; e.g. ``parse_game_directory([{'name': ...}])``."""
    if not isinstance(value, list):
        raise ValueError(f"Nexus games={type(value).__name__}: expected a list")
    pairs: dict[str, str] = {}
    for item in value:
        try:
            found = _game_pairs(item)
        except ValueError:
            continue  # One odd entry must not hide the other few thousand.
        for key, domain in found:
            pairs.setdefault(key, domain)
    return NexusGameDirectory(pairs)


def _cached_directory(games: object | None) -> NexusGameDirectory:
    try:
        return parse_game_directory(games) if games is not None else EMPTY_DIRECTORY
    except ValueError:
        return EMPTY_DIRECTORY


def _fresh_cache(cache: Path, now: float) -> object | None:
    try:
        if now - cache.stat().st_mtime > CACHE_MAX_AGE_SECONDS:
            return None
        return json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_cache(cache: Path, games: object) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=cache.parent, delete=False) as stream:
        json.dump(games, stream)
    os.replace(stream.name, cache)


def _stale_cache(cache: Path) -> object | None:
    return _fresh_cache(cache, cache.stat().st_mtime) if cache.is_file() else None


def _refreshed(cache: Path, api: NexusApi) -> NexusGameDirectory | None:
    try:
        games = api.games()
        directory = parse_game_directory(games)
    except (OSError, ValueError):
        # Offline or a Nexus outage must not break the game scan.
        return None
    _write_cache(cache, games)
    return directory


def load_game_directory(
    cache: Path, api: NexusApi | None, now: float
) -> NexusGameDirectory:
    """Read the cache or refresh it; e.g. ``load_game_directory(path, api, time())``."""
    games = _fresh_cache(cache, now)
    if games is None and api is not None:
        refreshed = _refreshed(cache, api)
        if refreshed is not None:
            return refreshed
    # Without a key or a connection, an old list still beats matching nothing.
    return _cached_directory(games if games is not None else _stale_cache(cache))
