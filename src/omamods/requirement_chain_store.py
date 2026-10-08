"""Keep a running requirement chain on disk so it survives a TUI restart.

Downloads keep arriving through the nxm handler while the TUI is closed; on
the next start the chain resumes, installs what arrived, and asks for the
rest. Before this file existed a restart silently dropped the chain halfway
(RED4ext installed, ArchiveXL staged, five requirements never requested).
"""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile

from omamods.nexus_api import NexusFile
from omamods.requirement_chain import ChainStep


@dataclass(frozen=True)
class SavedChain:
    """Which game a chain installs into and its steps, target last."""

    game_id: str
    steps: tuple[ChainStep, ...]


def chain_record_path(root: Path) -> Path:
    """Name the one chain record; e.g. ``chain_record_path(storage_root)``."""
    return root / "state" / "requirement_chain.json"


def save_chain(path: Path, saved: SavedChain) -> None:
    """Write atomically; e.g. ``save_chain(path, SavedChain('cyberpunk-2077', steps))``."""
    body = {"game_id": saved.game_id, "steps": [asdict(s) for s in saved.steps]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(body, stream, indent=2)
    os.replace(stream.name, path)


def _step(value: object) -> ChainStep:
    if not isinstance(value, dict):
        raise ValueError(f"chain step={value!r}: expected an object")
    files = tuple(NexusFile(**item) for item in value["files"])
    return ChainStep(value["mod_id"], value["name"], files, value["is_target"])


def load_chain(path: Path) -> SavedChain | None:
    """Read a saved chain if one exists; e.g. ``load_chain(path)``."""
    if not path.is_file():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        steps = tuple(_step(item) for item in body["steps"])
        game_id = body["game_id"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"requirement chain={str(path)!r}: expected game_id and steps"
        ) from error
    if not isinstance(game_id, str) or not steps or not steps[-1].is_target:
        raise ValueError(
            f"requirement chain={str(path)!r}: expected a game ID and steps "
            "ending with the target mod"
        )
    return SavedChain(game_id, steps)


def clear_chain(path: Path) -> None:
    """Forget a finished or failed chain; e.g. ``clear_chain(path)``."""
    path.unlink(missing_ok=True)
