"""A deliberately read-only boundary for discovery."""

from pathlib import Path
from typing import Protocol


class ReadableFiles(Protocol):
    """Expose only the filesystem operations discovery needs."""

    def read_text(self, path: Path) -> str:
        """Read UTF-8 text; for example, ``files.read_text(manifest)``."""
        ...

    def is_dir(self, path: Path) -> bool:
        """Check a directory; for example, ``files.is_dir(steam_root)``."""
        ...

    def glob(self, path: Path, pattern: str) -> tuple[Path, ...]:
        """Find files; for example, ``files.glob(root, '*/game.yml')``."""
        ...

    def resolve(self, path: Path) -> Path:
        """Canonicalize aliases; for example, ``files.resolve(steam_root)``."""
        ...


class LocalFiles:
    """Read the host filesystem without offering mutation operations."""

    def read_text(self, path: Path) -> str:
        """Accept Steam's optional BOM; e.g. ``files.read_text(app_manifest)``."""
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeError as error:
            raise ValueError(f"{path}: expected UTF-8 text: {error}") from error

    def is_dir(self, path: Path) -> bool:
        """Check host directories; for example, ``files.is_dir(Path('/tmp'))``."""
        return path.is_dir()

    def glob(self, path: Path, pattern: str) -> tuple[Path, ...]:
        """Return stable results; for example, ``files.glob(root, '*/game.yml')``."""
        return tuple(sorted(path.glob(pattern)))

    def resolve(self, path: Path) -> Path:
        """Deduplicate symlinks; for example, ``files.resolve(steam_alias)``."""
        return path.resolve()
