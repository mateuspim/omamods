"""Render home-screen rows, the game detail card, and the setup bar as Rich text."""

from pathlib import Path

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual.widgets.option_list import Option

from omamods.game_shelf import CATALOG, LIBRARY, MOD_READY, GameShelf, ShelfEntry
from omamods.installed_games import InstalledGame
from omamods.pak_games import PakOverlayGame
from omamods.tui.list_filter import mark_matches, matches_query

SECTION_TITLES: dict[str, str] = {
    MOD_READY: "MOD-READY",
    CATALOG: "IN THE CATALOG",
    LIBRARY: "YOUR OTHER GAMES",
}
SECTION_BADGES: dict[str, str] = {
    MOD_READY: "Mod-ready",
    CATALOG: "Catalog, not installable yet",
    LIBRARY: "Not in the catalog",
}
SECTION_PREFIX = "section:"
READY_DOT = ("●", "green")
INCOMPLETE_DOT = ("◐", "yellow")
MISSING_DOT = ("○", "bright_black")


def format_size(size_bytes: int | None) -> str:
    """Show bytes as GB or MB; for example, ``format_size(52_300_000_000)``."""
    if size_bytes is None:
        return "unknown"
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    return f"{size_bytes / 1_000_000:.0f} MB"


def install_dot(entry: ShelfEntry) -> tuple[str, str]:
    """Pick a status mark; for example, ``install_dot(entry) == ('●', 'green')``."""
    install = entry.install
    if install is None:
        return MISSING_DOT
    return READY_DOT if install.ready else INCOMPLETE_DOT


def entry_prompt(entry: ShelfEntry, query: str = "") -> Table:
    """Render one list row as mark, name, store; e.g. ``Option(entry_prompt(e, 'sb'))``."""
    dot, colour = install_dot(entry)
    install = entry.install
    row = Table.grid(expand=True, padding=(0, 1))
    row.add_column(width=2, style=colour)
    # Long titles (the Metal Gear collection) used to wrap onto two rows.
    row.add_column(ratio=1, no_wrap=True, overflow="ellipsis", style="bold")
    row.add_column(justify="right", no_wrap=True, style="dim italic")
    name = mark_matches(entry.name, query)
    row.add_row(f" {dot}", name, install.store if install else "not installed")
    return row


def section_heading(section: str, count: int) -> Option:
    """Make an unselectable group title; e.g. ``section_heading(MOD_READY, 2)``."""
    label = Text(f"{SECTION_TITLES[section]} · {count}", style="bold underline")
    return Option(label, id=f"{SECTION_PREFIX}{section}", disabled=True)


def shelf_options(shelf: GameShelf, query: str = "") -> list[Option]:
    """List each section's games matching query; e.g. ``shelf_options(s, 'blade')``."""
    options: list[Option] = []
    for section in SECTION_TITLES:
        entries = [e for e in shelf.section(section) if matches_query(e.name, query)]
        if not entries:
            continue
        options.append(section_heading(section, len(entries)))
        options.extend(Option(entry_prompt(e, query), id=e.key) for e in entries)
    return options


def _facts(entry: ShelfEntry, install: InstalledGame | None) -> Table:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", no_wrap=True)
    grid.add_column(overflow="fold")
    rows: list[tuple[str, str | Path | None]] = [
        ("Store", install.store if install else None),
        ("Folder", install.install_path if install else None),
        ("Library", install.library if install else None),
        ("Size", format_size(install.size_bytes) if install else None),
        ("App ID", install.app_id if install else _catalog_app_id(entry)),
        ("Build", install.build_id if install else None),
        ("Proton prefix", install.proton_prefix if install else None),
    ]
    for label, value in rows:
        if value is not None:
            grid.add_row(label, str(value))
    return grid


def _catalog_app_id(entry: ShelfEntry) -> str | None:
    app_id = entry.manifest.steam_app_id if entry.manifest else None
    return str(app_id) if app_id else None


def _status_line(entry: ShelfEntry) -> Text:
    dot, colour = install_dot(entry)
    install = entry.install
    if install is None:
        state = "Not installed"
    else:
        state = "Installed" if install.ready else "Incomplete or updating"
    text = Text.assemble((f"{dot} {state}", colour))
    text.append(f"   {section_badge(entry)}", style="magenta")
    return text


def section_badge(entry: ShelfEntry) -> str:
    """Label the entry's support; e.g. ``section_badge(e) == 'Mod-ready'``."""
    game = entry.pak_game
    if game is None or game.install_root is None:
        return SECTION_BADGES[entry.section]
    engine = "Unreal" if game.patch_chain is None else "RE Engine"
    return f"Mod-ready (auto-detected {engine} game)"


def _scanned_game_notes(entry: ShelfEntry) -> Text:
    game = entry.pak_game
    if game is None or game.install_root is None:
        return Text()
    if game.patch_chain is not None:
        return _patch_chain_notes(game.install_root, game)
    folder = game.install_root / game.paks_subpath / game.mods_dirname
    text = Text(f"\nMods go to {folder} (Nexus: {game.nexus_domain}).", style="dim")
    if game.signed:
        text.append(
            "\n⚠ This game ships .sig files and may refuse unsigned mod paks; "
            "check the mod page for a signature or bypass.",
            style="yellow",
        )
    return text


def _patch_chain_notes(root: Path, game: PakOverlayGame) -> Text:
    text = Text(
        f"\nPak mods become the next {game.patch_chain}.patch_NNN.pak in {root} "
        f"(Nexus: {game.nexus_domain}).",
        style="dim",
    )
    return text.append(
        "\n⚠ A game update can add an official patch with the same number; "
        "reinstall mods after updating. Loose natives/ files are packed into one "
        "patch; REFramework and DLL mods are refused.",
        style="yellow",
    )


def _mod_support(entry: ShelfEntry, staged_mods: int | None) -> Text:
    if entry.section == MOD_READY:
        staged = "" if staged_mods is None else f" · {staged_mods} mod(s) staged"
        text = Text(f"Enter manages this game's mods{staged}.", style="green")
        return text.append_text(_scanned_game_notes(entry))
    if entry.unreal is not None:
        return _unmatched_note("Unreal Engine", entry.name)
    if entry.patch_chain is not None:
        return _unmatched_note("RE Engine", entry.name)
    if entry.section == CATALOG:
        adapter = entry.manifest.adapter if entry.manifest else "undecided"
        return Text(f"Adapter planned: {adapter}. Installing is not supported yet.")
    return Text("Not in the OmaMods catalog yet; o opens its folder.", style="dim")


def _unmatched_note(engine: str, name: str) -> Text:
    return Text(
        f"{engine} game, but no Nexus game page matched {name!r}. "
        "Matching needs a Nexus API key (K) once; then r rescans.",
        style="yellow",
    )


def _notes(entry: ShelfEntry) -> Text:
    notes = entry.manifest.notes if entry.manifest else ()
    return Text("\n".join(f"• {note}" for note in notes), style="dim")


def entry_detail(entry: ShelfEntry, staged_mods: int | None) -> RenderableType:
    """Render the right-hand card; e.g. ``detail.update(entry_detail(entry, 3))``."""
    return Group(
        Text(entry.name, style="bold reverse"),
        _status_line(entry),
        Text(),
        _facts(entry, entry.install),
        Text(),
        _mod_support(entry, staged_mods),
        _notes(entry),
    )


def _check(ok: bool, label: str, missing_hint: str) -> Text:
    if ok:
        return Text.assemble(("✔ ", "green"), label)
    return Text.assemble(("✘ ", "red"), label, (f" ({missing_hint})", "dim"))


def setup_summary(shelf: GameShelf | None, has_api_key: bool) -> Text:
    """Summarise setup and discovery; e.g. ``setup_summary(shelf, True).plain``."""
    text = _check(has_api_key, "Nexus API key", "press K")
    text.append("   ")
    if shelf is None:
        return text.append("Scanning Steam and Heroic…", style="italic")
    libraries = f"{len(shelf.libraries)} Steam libraries"
    text.append_text(_check(bool(shelf.libraries), libraries, "use --steam-root"))
    installed = sum(1 for entry in shelf.entries if entry.install)
    text.append(f" · {installed} games installed", style="dim")
    if shelf.warnings:
        text.append(f"   ⚠ {len(shelf.warnings)} warning(s), w lists them", "yellow")
    return text
