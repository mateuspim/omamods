"""Plain-text CLI reports for discovery evidence."""

from omamods.steam_apps import AppInstallation, GameInspection
from omamods.steam_libraries import LibraryScan


def render_game_list(inspections: tuple[GameInspection, ...]) -> str:
    """List supported games; for example, ``print(render_game_list(inspections))``."""
    rows = ["GAME\tNAME\tADAPTER\tINSTALLATION"]
    rows.extend(
        f"{item.game.id}\t{item.game.name}\t{item.game.adapter}\t{item.status}"
        for item in inspections
    )
    return "\n".join(rows)


def _installation_lines(app: AppInstallation) -> list[str]:
    return [
        f"  Library: {app.library}",
        f"  Game directory: {app.install_path}",
        f"  Game directory present: {'yes' if app.files_present else 'no'}",
        f"  Steam marks fully installed: {'yes' if app.fully_installed else 'no'}",
        f"  Steam build ID: {app.build_id or 'unknown'}",
        f"  Proton prefix: {app.proton_prefix or 'not found'}",
    ]


def _inspection_heading(inspection: GameInspection, scan: LibraryScan) -> list[str]:
    game = inspection.game
    return [
        f"{game.name} ({game.id})",
        f"Adapter: {game.adapter} ({game.status})",
        f"Steam app ID: {game.steam_app_id or 'unconfigured'}",
        f"Installation: {inspection.status}",
        f"Steam libraries found: {len(scan.libraries)}",
        *(f"  {library}" for library in scan.libraries),
    ]


def render_inspection(inspection: GameInspection, scan: LibraryScan) -> str:
    """Explain inspection evidence; e.g. ``print(render_inspection(result, scan))``."""
    lines = _inspection_heading(inspection, scan)
    if inspection.game.steam_app_id is None:
        lines.append(
            "Set a verified steam_app_id in game.yml to match an installation."
        )
    for app in inspection.installations:
        lines.extend(_installation_lines(app))
    lines.extend(f"Note: {note}" for note in inspection.game.notes)
    lines.append(
        "Read-only discovery; Steam build IDs do not verify executable versions."
    )
    return "\n".join(lines)
