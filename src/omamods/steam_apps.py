"""Inspect declared Steam app IDs using local app manifests."""

from dataclasses import dataclass
from pathlib import Path

from omamods.filesystem import ReadableFiles
from omamods.keyvalues import KeyValues, keyvalues_block, parse_keyvalues
from omamods.manifests import GameManifest
from omamods.steam_libraries import LibraryScan


@dataclass(frozen=True)
class AppInstallation:
    """Steam metadata is evidence of installation, not executable verification."""

    library: Path
    install_path: Path
    build_id: str | None
    files_present: bool
    fully_installed: bool
    proton_prefix: Path | None


@dataclass(frozen=True)
class GameInspection:
    """A catalog game matched to zero or more local Steam installations."""

    game: GameManifest
    installations: tuple[AppInstallation, ...]
    warnings: tuple[str, ...]

    @property
    def status(self) -> str:
        """Summarize evidence; for example, ``inspection.status == 'installed'``."""
        if self.game.steam_app_id is None:
            return "app-id-unconfigured"
        if any(app.files_present and app.fully_installed for app in self.installations):
            return "installed"
        if self.installations:
            return "incomplete-install"
        if self.warnings:
            return "discovery-incomplete"
        return "not-found"


def decimal_field(fields: KeyValues, key: str) -> str:
    """Read a numeric manifest field; e.g. ``decimal_field(fields, 'appid')``."""
    value = fields.get(key)
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError(f"{key}={value!r}: expected a decimal integer string")
    return value


def install_directory(fields: KeyValues) -> str:
    """Read a safe folder name; e.g. ``install_directory(fields) == 'StellarBlade'``."""
    value = fields.get("installdir")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"installdir={value!r}: expected one nonempty directory name")
    if value in (".", "..") or any(char in value for char in ("/", "\\", "\0")):
        raise ValueError(
            f"installdir={value!r}: expected one directory name without traversal"
        )
    return value


def _installation(
    fields: KeyValues, library: Path, app_id: int, files: ReadableFiles
) -> AppInstallation:
    recorded_id = decimal_field(fields, "appid")
    if recorded_id != str(app_id):
        raise ValueError(f"appid={recorded_id!r}: expected {str(app_id)!r}")
    install_path = library / "steamapps/common" / install_directory(fields)
    return AppInstallation(
        library=library,
        install_path=install_path,
        build_id=build_id(fields),
        files_present=files.is_dir(install_path),
        fully_installed=steam_marks_installed(fields),
        proton_prefix=proton_prefix(library, app_id, files),
    )


def build_id(fields: KeyValues) -> str | None:
    """Read the optional build; e.g. ``build_id(fields) == '1234'``."""
    return decimal_field(fields, "buildid") if "buildid" in fields else None


def steam_marks_installed(fields: KeyValues) -> bool:
    """Check StateFlags bit 4; e.g. ``steam_marks_installed({'StateFlags': '4'})``."""
    return bool(int(decimal_field(fields, "StateFlags")) & 4)


def proton_prefix(library: Path, app_id: int, files: ReadableFiles) -> Path | None:
    """Find a Wine prefix; e.g. ``proton_prefix(Path('/steam'), 3489700, files)``."""
    prefix = library / f"steamapps/compatdata/{app_id}/pfx"
    return prefix if files.is_dir(prefix) else None


def _read_installation(
    library: Path, app_id: int, files: ReadableFiles
) -> AppInstallation | None:
    path = library / f"steamapps/appmanifest_{app_id}.acf"
    try:
        source = files.read_text(path)
    except FileNotFoundError:
        return None
    try:
        fields = keyvalues_block(parse_keyvalues(source), "AppState")
        return _installation(fields, library, app_id, files)
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error


def inspect_game(
    game: GameManifest, scan: LibraryScan, files: ReadableFiles
) -> GameInspection:
    """Match IDs, never titles; for example, ``inspect_game(game, scan, files)``."""
    installations: list[AppInstallation] = []
    warnings = list(scan.warnings)
    if game.steam_app_id is None:
        return GameInspection(game, (), tuple(warnings))
    for library in scan.libraries:
        try:
            installation = _read_installation(library, game.steam_app_id, files)
            if installation is not None:
                installations.append(installation)
        except (OSError, ValueError) as error:
            warnings.append(str(error))
    return GameInspection(game, tuple(installations), tuple(warnings))
