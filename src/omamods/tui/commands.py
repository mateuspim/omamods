"""Vim-style ':' commands: parsing, prefix resolution, and argument matching."""

from dataclasses import dataclass
import shlex

from omamods.mod_plan import STALE_CATEGORIES
from omamods.nexus_api import NexusFile
from omamods.pak_games import PakOverlayGame


@dataclass(frozen=True)
class CommandSpec:
    """One ':' command: its name, short aliases, usage, and help line."""

    name: str
    aliases: tuple[str, ...]
    usage: str
    summary: str


@dataclass(frozen=True)
class ParsedCommand:
    """A command line split into its word and arguments."""

    word: str
    args: tuple[str, ...]


GLOBAL_COMMANDS = (
    CommandSpec("quit", ("q",), ":q", "close this screen (quit on the home screen)"),
    CommandSpec("quitall", ("qa", "qa!"), ":qa", "quit OmaMods"),
    CommandSpec("help", ("h",), ":help", "list the commands for this screen"),
    CommandSpec("game", ("e",), ":game <name>", "open a game, e.g. :game sb"),
    CommandSpec("queue", ("downloads",), ":queue", "open the download queue"),
    CommandSpec("key", (), ":key <api-key>", "save your Nexus API key"),
    CommandSpec("nxm", (), ":nxm", "make browsers send nxm links to OmaMods"),
    CommandSpec("add", (), ":add <url>", "add a mod by its Nexus or AyakaMods URL"),
    CommandSpec(
        "ayaka-login",
        (),
        ":ayaka-login [xf_user]",
        "save your AyakaMods login; without a value, guides you",
    ),
)


def parse_command(text: str) -> ParsedCommand | None:
    """Split a ':' line; e.g. ``parse_command(':install Hair')``."""
    try:
        words = shlex.split(text.strip().removeprefix(":"))
    except ValueError as error:
        raise ValueError(f"command={text!r}: expected balanced quotes") from error
    if not words:
        return None
    return ParsedCommand(words[0].lower(), tuple(words[1:]))


def resolve_command(word: str, specs: tuple[CommandSpec, ...]) -> CommandSpec:
    """Match exactly, by alias, or by unique prefix like vim; e.g. ``resolve_command('inst', s)``."""
    for spec in specs:
        if word == spec.name or word in spec.aliases:
            return spec
    matches = [spec for spec in specs if spec.name.startswith(word)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        names = ", ".join(f":{spec.name}" for spec in matches)
        raise ValueError(f"E464: Ambiguous use of :{word} ({names})")
    raise ValueError(f"E492: Not an editor command: {word}  (try :help)")


def help_text(specs: tuple[CommandSpec, ...]) -> str:
    """Render ':help'; for example, ``help_text(GLOBAL_COMMANDS)``."""
    width = max(len(spec.usage) for spec in specs)
    return "\n".join(f"{spec.usage.ljust(width)}  {spec.summary}" for spec in specs)


def _name_matches(files: tuple[NexusFile, ...], needle: str) -> list[NexusFile]:
    names = [(f, f.display_name.lower(), f.file_name.lower()) for f in files]
    exact = [f for f, shown, stored in names if needle in (shown, stored)]
    return exact or [
        f for f, shown, stored in names if needle in shown or needle in stored
    ]


def find_file(files: tuple[NexusFile, ...], query: str) -> NexusFile:
    """Pick a file by ID or unique name part; e.g. ``find_file(files, 'Hair')``."""
    if query.isdecimal():
        by_id = [file for file in files if file.file_id == int(query)]
        if by_id:
            return by_id[0]
    matches = _name_matches(files, query.lower())
    current = [f for f in matches if f.category not in STALE_CATEGORIES]
    if len(matches) > 1 and len(current) == 1:
        return current[0]  # e.g. MAIN 1.1 over an OLD_VERSION 1.0 of the same name.
    if len(matches) != 1:
        found = [f"{f.file_id}:{f.display_name or f.file_name}" for f in matches]
        raise ValueError(
            f"file={query!r}: expected one match by ID or name, got {found}"
        )
    return matches[0]


def _initials(name: str) -> str:
    return "".join(word[0] for word in name.replace("-", " ").split()).lower()


def find_game(games: tuple[PakOverlayGame, ...], query: str) -> PakOverlayGame:
    """Pick a game by ID prefix, name part, or initials; e.g. ``find_game(g, 'sb')``."""
    needle = query.lower()
    matches = [
        game
        for game in games
        if game.game_id.startswith(needle)
        or needle in game.name.lower()
        or needle == _initials(game.name)
    ]
    if len(matches) != 1:
        names = [game.game_id for game in games]
        raise ValueError(f"game={query!r}: expected one of {names} (or initials)")
    return matches[0]
