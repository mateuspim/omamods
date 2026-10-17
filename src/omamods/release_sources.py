"""Name the Codeberg and GitHub repositories whose releases OmaMods installs.

Some fixes are published only as repository releases, never on Nexus: Lyall's
MGSVFix lives at codeberg.org/Lyall/MGSVFix (its GitHub copy is archived at
0.0.2). Each source gets a small fixed mod ID of its own, since these sites
have no mod numbers; staging keeps them apart from Nexus and AyakaMods IDs.
"""

from dataclasses import dataclass

# Web and API roots; both serve GET /repos/<owner>/<repo>/releases/latest.
FORGES: dict[str, tuple[str, str]] = {
    "codeberg": ("https://codeberg.org", "https://codeberg.org/api/v1"),
    "github": ("https://github.com", "https://api.github.com"),
}


@dataclass(frozen=True)
class ReleaseSource:
    """One repository whose newest release is a game's mod."""

    mod_id: int
    game_id: str
    forge: str
    owner: str
    repo: str
    summary: str

    @property
    def page_url(self) -> str:
        """Link the repository; e.g. ``source.page_url``."""
        return f"{_forge(self.forge)[0]}/{self.owner}/{self.repo}"

    @property
    def latest_release_url(self) -> str:
        """Ask the API for the newest release; e.g. ``source.latest_release_url``."""
        api = _forge(self.forge)[1]
        return f"{api}/repos/{self.owner}/{self.repo}/releases/latest"


def _forge(forge: str) -> tuple[str, str]:
    roots = FORGES.get(forge)
    if roots is None:
        raise ValueError(f"forge={forge!r}: expected one of {sorted(FORGES)!r}")
    return roots


RELEASE_SOURCES: tuple[ReleaseSource, ...] = (
    ReleaseSource(
        mod_id=1,
        game_id="metalgearsolidvtpp",
        forge="codeberg",
        owner="Lyall",
        repo="MGSVFix",
        summary=(
            "Ultrawide support with HUD and effect fixes, unlocked resolutions, "
            "and an unlocked framerate. Settings live in MGSVFix.ini beside "
            "mgsvtpp.exe. Lens dirt still renders at 16:9."
        ),
    ),
)


def sources_for(game_id: str) -> tuple[ReleaseSource, ...]:
    """List a game's release mods; e.g. ``sources_for('metalgearsolidvtpp')``."""
    return tuple(source for source in RELEASE_SOURCES if source.game_id == game_id)


def release_source(game_id: str, mod_id: int) -> ReleaseSource:
    """Look one up; e.g. ``release_source('metalgearsolidvtpp', 1)``."""
    for source in sources_for(game_id):
        if source.mod_id == mod_id:
            return source
    known = [source.mod_id for source in sources_for(game_id)]
    raise ValueError(
        f"release mod={game_id}/{mod_id}: expected one of the IDs {known!r}"
    )
