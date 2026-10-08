"""Named, deterministic substitutes for filesystem, Nexus, and archive I/O."""

from io import BytesIO
import json
from pathlib import Path
import struct

from omamods.cdn_download import (
    NexusHttpError,
    ProgressCallback,
    TransientDownloadError,
    copy_with_progress,
)
from omamods.ayaka_download import AyakaReply
from omamods.game_shelf import GameShelf
from omamods.nexus_config import UserSettings


class FakeFiles:
    """Model read operations without touching the developer's Steam installation."""

    def __init__(
        self,
        contents: dict[Path, str] | None = None,
        directories: tuple[Path, ...] = (),
        aliases: dict[Path, Path] | None = None,
        failures: dict[Path, OSError] | None = None,
    ) -> None:
        self.contents = contents or {}
        self.directories = set(directories)
        self.aliases = aliases or {}
        self.failures = failures or {}
        self.reads: list[Path] = []

    def read_text(self, path: Path) -> str:
        """Track reads; for example, ``fake.read_text(Path('/steam/test.acf'))``."""
        self.reads.append(path)
        if path in self.failures:
            raise self.failures[path]
        if path not in self.contents:
            raise FileNotFoundError(f"{path}: expected an existing file")
        return self.contents[path]

    def is_dir(self, path: Path) -> bool:
        """Use declared directories; for example, ``fake.is_dir(Path('/steam'))``."""
        return self.resolve(path) in self.directories

    def glob(self, path: Path, pattern: str) -> tuple[Path, ...]:
        """Find fixture manifests; for example, ``fake.glob(Path('games'), '*/game.yml')``."""
        return tuple(
            sorted(item for item in self.contents if item.match(str(path / pattern)))
        )

    def resolve(self, path: Path) -> Path:
        """Resolve declared aliases; for example, ``fake.resolve(Path('/alias'))``."""
        return self.aliases.get(path, path)


class FakePath:
    """Path-shaped fake for testing LocalFiles without real filesystem I/O."""

    def __init__(self, text: str = "text", error: UnicodeError | None = None) -> None:
        self.text = text
        self.error = error
        self.encoding: str | None = None

    def read_text(self, encoding: str) -> str:
        """Capture encoding; for example, ``path.read_text(encoding='utf-8-sig')``."""
        self.encoding = encoding
        if self.error:
            raise self.error
        return self.text

    def is_dir(self) -> bool:
        """Represent a directory; for example, ``path.is_dir()``."""
        return True

    def glob(self, pattern: str) -> tuple[Path, ...]:
        """Return unsorted entries; for example, ``path.glob('*/game.yml')``."""
        return (Path("z/game.yml"), Path("a/game.yml"))

    def resolve(self) -> Path:
        """Resolve to a fixed path; for example, ``path.resolve()``."""
        return Path("/resolved")


def sample_fields() -> dict[str, object]:
    """Provide isolated manifest fields; for example, ``fields = sample_fields()``."""
    return {
        "id": "demo",
        "name": "Demo Game",
        "status": "discovery",
        "platforms": ["steam"],
        "adapter": "undecided",
        "steam_app_id": 42,
    }


def app_text(app_id: str = "42", directory: str = "Demo", flags: str = "4") -> str:
    """Build Steam test metadata; for example, ``app_text(flags='2')``."""
    return (
        f'"AppState" {{ "appid" "{app_id}" "installdir" "{directory}" '
        f'"buildid" "12345" "StateFlags" "{flags}" }}'
    )


class FakeConfigFiles:
    """Retain private config content in memory."""

    def __init__(self) -> None:
        self.contents: dict[Path, str] = {}

    def read_text(self, path: Path) -> str:
        """Read recorded text; e.g. ``fake.read_text(path)``."""
        if path not in self.contents:
            raise FileNotFoundError(path)
        return self.contents[path]

    def create_private(self, path: Path, content: str) -> None:
        """Reject replacement; e.g. ``fake.create_private(path, text)``."""
        if path in self.contents:
            raise FileExistsError(path)
        self.contents[path] = content

    def replace_private(self, path: Path, content: str) -> None:
        """Overwrite text; e.g. ``fake.replace_private(path, text)``."""
        self.contents[path] = content


class FakeNexusTransport:
    """Return predictable API metadata and archive bytes."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self.downloads: list[str] = []
        self.archive = b"fake archive"

    def get_json(self, url: str, api_key: str) -> object:
        """Return one MAIN file or CDN link; e.g. ``fake.get_json(url, key)``."""
        self.requests.append(url)
        if url.endswith("files.json"):
            return {
                "files": [
                    {"file_id": 7, "file_name": "mod.zip", "category_name": "MAIN"}
                ]
            }
        return [{"URI": "https://cdn.example/mod.zip"}]

    def post_json(self, url: str, api_key: str, body: object) -> object:
        """Refuse; these tests never query GraphQL."""
        raise AssertionError(f"url={url!r}: expected no GraphQL queries")

    def download(
        self,
        url: str,
        destination: BytesIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Write fake archive; e.g. ``fake.download(url, stream)``."""
        self.downloads.append(url)
        destination.write(self.archive)


class FakeArchiveReader:
    """Expose chosen archive members without a real archive tool."""

    def __init__(self, contents: dict[str, bytes]) -> None:
        self.contents = contents

    def members(self, archive: Path) -> tuple[str, ...]:
        """List fake members; e.g. ``fake.members(path)``."""
        return tuple(self.contents)

    def copy_member(self, archive: Path, member: str, destination: BytesIO) -> None:
        """Write fake member; e.g. ``fake.copy_member(path, name, stream)``."""
        destination.write(self.contents[member])


class FakeNexusSite:
    """Answer mod info, file listings, and downloads like a small Nexus."""

    def __init__(self, premium: bool = True, picture_online: bool = True) -> None:
        self.premium = premium
        self.picture_online = picture_online
        self.fail_downloads = False
        self.broken_download_error: Exception | None = None
        self.old_version_ids: set[int] = set()
        self.archive = b"archive"
        self.connection_resets = 0
        self.bytes_before_reset = 3
        self.resume_offsets: list[int] = []
        self.requests: list[str] = []
        self.downloads: list[str] = []
        self.picture = b"picture"
        # Mod ID -> required mod IDs, served like Nexus' v2 GraphQL API.
        self.requirement_graph: dict[int, tuple[int, ...]] = {}
        self.queries: list[tuple[int, ...]] = []
        # Served as contains_adult_content in mod details.
        self.adult = False

    def post_json(self, url: str, api_key: str, body: object) -> object:
        """Answer requirement queries; e.g. ``site.post_json(url, key, body)``."""
        assert isinstance(body, dict)
        ids = tuple(item["modId"] for item in body["variables"]["ids"])
        self.queries.append(ids)
        nodes = [self._requirement_node(mod_id) for mod_id in ids]
        return {"data": {"legacyModsByDomain": {"nodes": nodes}}}

    def _requirement_node(self, mod_id: int) -> dict[str, object]:
        listed = [
            {
                "modId": str(needed),
                "modName": f"Mod {needed}",
                "gameId": "1",
                "externalRequirement": False,
                "url": "",
                "notes": "",
            }
            for needed in self.requirement_graph.get(mod_id, ())
        ]
        return {
            "modId": mod_id,
            "name": f"Mod {mod_id}",
            "gameId": 1,
            "modRequirements": {
                "nexusRequirements": {"nodes": listed},
                "dlcRequirements": [],
            },
        }

    def get_json(self, url: str, api_key: str) -> object:
        """Route by endpoint; e.g. ``site.get_json(url, key)``."""
        self.requests.append(url)
        if url.endswith("files.json"):
            return {
                "files": [
                    self._file(7, "Black.zip", "MAIN"),
                    self._file(8, "Hair.zip", "OPTIONAL"),
                ]
            }
        if "download_link" in url:
            return self._download_link(url)
        return {
            "name": "Sample Outfit",
            "summary": "A suit.",
            "author": "someone",
            "version": "1.0",
            "picture_url": "https://staticdelivery.nexusmods.com/suit.png",
            "contains_adult_content": self.adult,
        }

    def _file(self, file_id: int, name: str, category: str) -> dict[str, object]:
        if file_id in self.old_version_ids:
            category = "OLD_VERSION"
        return {
            "file_id": file_id,
            "file_name": name,
            "category_name": category,
            "uploaded_timestamp": 1,
            "name": name.removesuffix(".zip"),
            "version": "1.0",
            "size_kb": 2048,
        }

    def _download_link(self, url: str) -> object:
        if not self.premium and "key=" not in url:
            raise NexusHttpError(403, "a successful API response")
        return [{"URI": "https://cdn.example/" + url.split("/files/")[1]}]

    def download(
        self,
        url: str,
        destination: BytesIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Write picture or archive bytes; e.g. ``site.download(url, stream)``."""
        self.downloads.append(url)
        if url.endswith(".png") and not self.picture_online:
            raise NexusHttpError(404, "a downloadable file")
        if self.fail_downloads:
            raise NexusHttpError(503, "a downloadable file")
        if self.broken_download_error is not None:
            raise self.broken_download_error
        body = self.picture if url.endswith(".png") else self.archive
        self.resume_offsets.append(resume_from)
        if self.connection_resets:
            # Like mod 533's CDN: send part of the file, then drop the connection.
            self.connection_resets -= 1
            part = body[resume_from : resume_from + self.bytes_before_reset]
            copy_with_progress(
                BytesIO(part), destination, len(body), progress, resume_from
            )
            raise TransientDownloadError(
                "Nexus download interrupted: Connection reset by peer"
            )
        rest = BytesIO(body[resume_from:])
        copy_with_progress(rest, destination, len(body), progress, resume_from)


class FakeCommandRunner:
    """Record host commands and answer xdg-mime queries."""

    def __init__(self, exit_code: int = 0, output: str = "") -> None:
        self.commands: list[tuple[str, ...]] = []
        self.exit_code = exit_code
        self.output = output

    def run(self, command: tuple[str, ...]) -> tuple[int, str]:
        """Record a command; e.g. ``runner.run(('true',))``."""
        self.commands.append(command)
        return self.exit_code, self.output


class FakeLauncher:
    """Record GUI programs instead of starting them."""

    def __init__(self) -> None:
        self.launched: list[tuple[str, ...]] = []

    def launch(self, command: tuple[str, ...]) -> None:
        """Record a launch; e.g. ``launcher.launch(('imv', 'a.png'))``."""
        self.launched.append(command)


class FakeHyprland:
    """Answer xdg-settings and hyprctl like a Lua-config Hyprland session."""

    def __init__(
        self, clients: list[dict[str, object]], dispatch_reply: str = "ok"
    ) -> None:
        self.clients = clients
        self.dispatch_reply = dispatch_reply
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...]) -> tuple[int, str]:
        """Route by program; e.g. ``hyprland.run(('hyprctl', 'clients', '-j'))``."""
        self.commands.append(command)
        if command[:2] == ("hyprctl", "clients"):
            return 0, json.dumps(self.clients)
        if command[:2] == ("hyprctl", "dispatch"):
            return 0, self.dispatch_reply
        if command[0] == "xdg-settings":
            return 0, "brave-origin.desktop"
        return 0, ""

    def _dispatched(self, action: str) -> list[str]:
        return [
            c[2]
            for c in self.commands
            if c[:2] == ("hyprctl", "dispatch") and action in c[2]
        ]

    def closed(self) -> list[str]:
        """List dispatched close commands; e.g. ``hyprland.closed()``."""
        return self._dispatched("window.close")

    def hidden(self) -> list[str]:
        """List dispatched hide moves; e.g. ``hyprland.hidden()``."""
        return self._dispatched("special:omamods")


class FakeSleep:
    """Record retry waits instead of sleeping, keeping tests fast."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        """Record a wait; for example, ``sleep(2.0)``."""
        self.delays.append(seconds)


class FakeShelfScanner:
    """Return a fixed home-screen shelf and count scans, without touching Steam."""

    def __init__(self, shelf: GameShelf) -> None:
        self.shelf = shelf
        self.scans = 0

    def __call__(self, settings: UserSettings) -> GameShelf:
        """Hand back the fixture; for example, ``scanner(settings).entries``."""
        self.scans += 1
        return self.shelf


class FakeNexusGamesTransport:
    """Serve Nexus' game list, or fail like an offline host, and count requests."""

    def __init__(self, games: object, failure: Exception | None = None) -> None:
        self.games = games
        self.failure = failure
        self.requests: list[str] = []

    def get_json(self, url: str, api_key: str) -> object:
        """Return the game list; for example, ``fake.get_json(url, key)``."""
        self.requests.append(url)
        if self.failure is not None:
            raise self.failure
        return self.games

    def download(
        self,
        url: str,
        destination: BytesIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Refuse; the game list never downloads archives."""
        raise AssertionError(f"url={url!r}: expected no downloads")

    def post_json(self, url: str, api_key: str, body: object) -> object:
        """Refuse; the game list never queries GraphQL."""
        raise AssertionError(f"url={url!r}: expected no GraphQL queries")


class FakeModArchives:
    """Give each staged mod its own members, keyed by the mod ID in its path."""

    def __init__(self, members_by_mod: dict[int, dict[str, bytes]]) -> None:
        self.members_by_mod = members_by_mod

    def _members(self, archive: Path) -> dict[str, bytes]:
        # Staged archives live at archives/<game>/<mod_id>/<file_id>/<name>.
        return self.members_by_mod[int(archive.parent.parent.name)]

    def members(self, archive: Path) -> tuple[str, ...]:
        """List that mod's members; e.g. ``fake.members(path)``."""
        return tuple(self._members(archive))

    def copy_member(self, archive: Path, member: str, destination: BytesIO) -> None:
        """Write one member; e.g. ``fake.copy_member(path, name, stream)``."""
        destination.write(self._members(archive)[member])


def version_resource(major: int, minor: int, build: int, revision: int) -> bytes:
    header = struct.pack("<II", 0xFEEF04BD, 0x00010000)
    return header + struct.pack("<II", major << 16 | minor, build << 16 | revision)


class FakeDllFiles:
    """Serve DLL bytes by path; a missing path raises like a missing prefix."""

    def __init__(self, files: dict[Path, bytes]) -> None:
        self.files = files

    def __call__(self, path: Path) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(f"{path}: expected an existing DLL")
        return self.files[path]


class FakeAyakaPages:
    """Serve mod pages by URL; e.g. ``FakeAyakaPages({url: html})``."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requests: list[str] = []

    def get_text(self, url: str) -> str:
        """Return a stored page; e.g. ``fake.get_text(url)``."""
        self.requests.append(url)
        if url not in self.pages:
            raise ValueError(f"AyakaMods HTTP 404 for {url!r}: expected a page")
        return self.pages[url]


class FakeAyakaSession:
    """Answer download URLs like a logged-in AyakaMods; e.g. ``FakeAyakaSession()``."""

    def __init__(self) -> None:
        self.replies: dict[str, AyakaReply] = {}
        self.bodies: dict[str, bytes] = {}
        self.probes: list[str] = []
        self.downloads: list[str] = []
        self.cookies: list[str] = []

    def serve_file(self, url: str, name: str, body: bytes) -> None:
        """Answer ``url`` with a file; e.g. ``fake.serve_file(u, 'a.zip', b'zip')``."""
        self.replies[url] = AyakaReply(url, name, len(body), "")
        self.bodies[url] = body

    def serve_page(self, url: str, page_html: str, final_url: str = "") -> None:
        """Answer ``url`` with HTML, maybe after a redirect; e.g. ``fake.serve_page(u, h)``."""
        self.replies[url] = AyakaReply(final_url or url, None, None, page_html)

    def opener(self, cookie: str) -> "FakeAyakaSession":
        """Stand in for ``UrlAyakaSession``; e.g. ``TuiHost(..., ayaka_session=fake.opener)``."""
        self.cookies.append(cookie)
        return self

    def probe(self, url: str) -> AyakaReply:
        """Return the stored reply; e.g. ``fake.probe(url)``."""
        self.probes.append(url)
        if url not in self.replies:
            raise ValueError(f"AyakaMods HTTP 404 for {url!r}: expected a reply")
        return self.replies[url]

    def download(
        self,
        url: str,
        destination: BytesIO,
        progress: ProgressCallback | None = None,
        resume_from: int = 0,
    ) -> None:
        """Write the stored body; e.g. ``fake.download(url, stream)``."""
        self.downloads.append(url)
        body = self.bodies[url]
        copy_with_progress(
            BytesIO(body[resume_from:]), destination, len(body), progress, resume_from
        )
