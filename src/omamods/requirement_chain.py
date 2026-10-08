"""Download and install a mod's requirements one at a time, in order.

Without Premium every download is a click in its own Nexus window, so only
one is requested at a time; each file installs as soon as it arrives, before
anything that needs it.
"""

from dataclasses import dataclass, field
from typing import Protocol

from omamods.nexus_api import NexusFile


@dataclass(frozen=True)
class ChainStep:
    """One mod to install; the last step is the mod that asked for the rest."""

    mod_id: int
    name: str
    files: tuple[NexusFile, ...]
    # The requiring mod counts as installed only once all its files are; a
    # requirement counts once any version of it is.
    is_target: bool = False


class ChainHost(Protocol):
    """What the chain needs from staging and the installer."""

    def step_installed(self, step: ChainStep) -> bool:
        """Report the mod as present; e.g. ``host.step_installed(step)``."""
        ...

    def step_staged(self, step: ChainStep) -> bool:
        """Report every file downloaded; e.g. ``host.step_staged(step)``."""
        ...

    def install_step(self, step: ChainStep) -> int:
        """Install its files, returning a count; e.g. ``host.install_step(step)``."""
        ...

    def request_step(self, step: ChainStep) -> bool:
        """Start downloads; True once all are staged. E.g. ``host.request_step(step)``."""
        ...


@dataclass
class RequirementChain:
    """Walk steps on each tick; e.g. ``RequirementChain(steps).advance(host)``."""

    steps: tuple[ChainStep, ...]
    requested: set[int] = field(default_factory=set)
    finished: bool = False

    def advance(self, host: ChainHost) -> tuple[str, ...]:
        """Install what arrived and ask for what is next; e.g. ``chain.advance(host)``."""
        try:
            return self._walk(host)
        except (OSError, ValueError):
            # A failed download or install stops the chain: later mods need it.
            self.finished = True
            raise

    def _walk(self, host: ChainHost) -> tuple[str, ...]:
        messages: list[str] = []
        for step in self.steps:
            if host.step_installed(step):
                continue
            if not self._ready(step, host, messages):
                return tuple(messages)
            messages.append(f"{step.name}: installed {host.install_step(step)} files")
        self.finished = True
        return (*messages, f"{self.steps[-1].name}: it and its requirements are in")

    def _ready(self, step: ChainStep, host: ChainHost, messages: list[str]) -> bool:
        if host.step_staged(step):
            return True
        if step.mod_id in self.requested:
            return False
        self.requested.add(step.mod_id)
        if host.request_step(step):
            return True
        messages.append(f"{step.name}: waiting for its download")
        return False
