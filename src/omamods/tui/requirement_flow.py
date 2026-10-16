"""Plan and run "install a mod with everything it needs" for the TUI.

Only games that install into the game folder (Cyberpunk 2077) take part:
elsewhere requirements are loaders such as UE4SS, which a mod has to bundle.
Launch options are checked for every game with a Steam app ID.
"""

# The service owns a flow and the flow calls the service; only type checkers
# need the import, which would otherwise be circular.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import TYPE_CHECKING

from omamods.nexus_api import NexusFile, NexusPage
from omamods.nexus_requirements import (
    NexusRequirement,
    NexusRequirementsApi,
    RequirementTree,
    resolve_requirements,
)
from omamods.pak_games import PakOverlayGame
from omamods.red_frameworks import (
    PathProbe,
    frameworks_on_disk,
)
from omamods.launch_options_advice import LaunchOptionsAdvice, launch_options_advice
from omamods.proton_runtime import BytesReader, msvc_runtime_version, steam_prefix
from omamods.requirement_chain import ChainStep, RequirementChain
from omamods.requirement_chain_store import (
    SavedChain,
    chain_record_path,
    clear_chain,
    load_chain,
    save_chain,
)
from omamods.staging import StagedMod
from omamods.ue4ss_archive import BINARIES_FROM_PAKS, ue4ss_proxies_on_disk

if TYPE_CHECKING:
    from omamods.tui.service import ModsService


@dataclass(frozen=True)
class RequirementPlan:
    """What "install with requirements" would do, for the confirm dialog."""

    game: PakOverlayGame
    target: ChainStep
    steps: tuple[ChainStep, ...]
    present: tuple[str, ...]
    # Requirements with no MAIN file to pick; the person installs them.
    unresolved: tuple[str, ...]
    tree: RequirementTree
    # None for games without a Steam app ID to read launch options for.
    launch_advice: LaunchOptionsAdvice | None
    # Steps whose files are already downloaded and only need installing.
    staged: frozenset[int] = frozenset()

    @property
    def missing_dlls(self) -> tuple[str, ...]:
        """DLL overrides Steam lacks; e.g. ``plan.missing_dlls == ('winmm',)``."""
        return self.launch_advice.missing if self.launch_advice else ()

    @property
    def needs_work(self) -> bool:
        """True when requirements are missing; e.g. ``plan.needs_work``."""
        return bool(self.steps or self.unresolved)


def newest_main_file(files: tuple[NexusFile, ...]) -> NexusFile | None:
    """Pick the file to install; e.g. ``newest_main_file(api.files(page))``."""
    mains = [file for file in files if file.category == "MAIN"]
    return max(mains, key=lambda file: file.uploaded_timestamp, default=None)


class ServiceChainHost:
    """Run chain steps through the TUI service; e.g. ``ServiceChainHost(s, cp, p)``."""

    def __init__(
        self, service: ModsService, game: PakOverlayGame, exists: PathProbe
    ) -> None:
        self.service = service
        self.game = game
        self.exists = exists

    def _staged(self, step: ChainStep) -> StagedMod:
        return self.service.staged_mod(self.game, step.mod_id)

    def step_installed(self, step: ChainStep) -> bool:
        """Report the mod as present; e.g. ``host.step_installed(step)``."""
        installed = self._staged(step).installed
        if step.is_target:
            return all(file.file_id in installed for file in step.files)
        return bool(installed) or step.mod_id in self.frameworks_present()

    def frameworks_present(self) -> frozenset[int]:
        """Frameworks found in the game folder; e.g. ``host.frameworks_present()``."""
        root = self.service.host.locate_paks(self.game, self.service.settings)
        return frameworks_on_disk(root, self.exists)

    def step_staged(self, step: ChainStep) -> bool:
        """Report every file downloaded; e.g. ``host.step_staged(step)``."""
        archives = self._staged(step).archives
        return all(file.file_id in archives for file in step.files)

    def install_step(self, step: ChainStep) -> int:
        """Install each file without a variant; e.g. ``host.install_step(step)``."""
        installed = self._staged(step).installed
        return sum(
            self.service.install(self.game, step.mod_id, file.file_id, None)
            for file in step.files
            if file.file_id not in installed
        )

    def request_step(self, step: ChainStep) -> bool:
        """Stage details, then download; e.g. ``host.request_step(step)``."""
        url = self.service.mod_page_url(self.game, step.mod_id)
        self.service.fetch_mod(self.game, url)
        self.service.mark_queued(self.game, step.mod_id, step.files)
        fetched = [
            self.service.fetch_file(self.game, step.mod_id, f) for f in step.files
        ]
        return all(fetched)


class RequirementFlow:
    """Plan and drive requirement installs; e.g. ``RequirementFlow(service)``."""

    def __init__(
        self,
        service: ModsService,
        exists: PathProbe = Path.exists,
        read_bytes: BytesReader = Path.read_bytes,
    ) -> None:
        self.service = service
        self.exists = exists
        self.read_bytes = read_bytes
        self.chain: RequirementChain | None = None
        self.chain_host: ServiceChainHost | None = None
        # Ticks come from a timer; a slow install must not run twice at once.
        self.lock = threading.Lock()
        self.record = chain_record_path(service.settings.storage_root)
        self.resume_error: str | None = None
        self._resume()

    def _resume(self) -> None:
        try:
            saved = load_chain(self.record)
            if saved is not None:
                game = self.service.catalog.get(saved.game_id)
                self._run(game, saved.steps)
        except ValueError as error:
            # Reported on the first tick, where notifications can show it.
            self.resume_error = f"Could not resume requirement installs: {error}"
            clear_chain(self.record)

    def _run(self, game: PakOverlayGame, steps: tuple[ChainStep, ...]) -> None:
        self.chain = RequirementChain(steps)
        self.chain_host = ServiceChainHost(self.service, game, self.exists)

    def plan(
        self, game: PakOverlayGame, mod: StagedMod, files: tuple[NexusFile, ...]
    ) -> RequirementPlan:
        """Resolve requirements; e.g. ``flow.plan(cyberpunk, staged, files)``."""
        api = NexusRequirementsApi(
            self.service.host.transport, self.service.settings.api_key
        )
        tree = resolve_requirements(api, game.nexus_domain, mod.mod_id)
        host = ServiceChainHost(self.service, game, self.exists)
        target = ChainStep(mod.mod_id, mod.title, files, True)
        present = tuple(r.name for r in tree.order if self._present(host, r))
        missing = tuple(r for r in tree.order if not self._present(host, r))
        steps, unresolved = self._steps(game, missing)
        advice = self.launch_advice(game, frozenset(r.mod_id for r in tree.order))
        staged = frozenset(s.mod_id for s in (*steps, target) if host.step_staged(s))
        return RequirementPlan(
            game, target, steps, present, unresolved, tree, advice, staged
        )

    def _present(self, host: ServiceChainHost, requirement: NexusRequirement) -> bool:
        return host.step_installed(ChainStep(requirement.mod_id, requirement.name, ()))

    def _steps(
        self, game: PakOverlayGame, missing: tuple[NexusRequirement, ...]
    ) -> tuple[tuple[ChainStep, ...], tuple[str, ...]]:
        api = self.service.nexus_api()
        steps: list[ChainStep] = []
        unresolved: list[str] = []
        for requirement in missing:
            files = api.files(NexusPage(game.nexus_domain, requirement.mod_id))
            main = newest_main_file(files)
            if main is None:
                unresolved.append(requirement.name)
                continue
            steps.append(ChainStep(requirement.mod_id, requirement.name, (main,)))
        return tuple(steps), tuple(unresolved)

    def launch_advice(
        self, game: PakOverlayGame, planned: frozenset[int] = frozenset()
    ) -> LaunchOptionsAdvice | None:
        """Compare Steam's launch options with installed and planned frameworks.

        Example: ``flow.launch_advice(cyberpunk).suggested``.
        """
        if game.steam_app_id is None:
            return None
        app_id = game.steam_app_id
        options = self.service.host.read_launch_options(app_id)
        root = self.service.host.locate_paks(game, self.service.settings)
        if not game.redengine:
            return self._unreal_advice(options, root, app_id)
        host = ServiceChainHost(self.service, game, self.exists)
        wanted = planned | host.frameworks_present()
        runtime = msvc_runtime_version(steam_prefix(root, app_id), self.read_bytes)
        return launch_options_advice(options, wanted, runtime, app_id)

    def _unreal_advice(
        self, options: tuple[str, ...], paks: Path, app_id: str
    ) -> LaunchOptionsAdvice:
        # An installed UE4SS bundle needs its proxy DLL (dwmapi) overridden.
        loaders = ue4ss_proxies_on_disk(paks / BINARIES_FROM_PAKS, self.exists)
        return launch_options_advice(options, frozenset(), None, app_id, loaders)

    def start(self, plan: RequirementPlan) -> RequirementChain:
        """Begin installing; e.g. ``flow.start(plan)``."""
        if self.running and self.chain is not None:
            raise ValueError(
                f"requirement chain for {self.chain.steps[-1].name!r}: expected "
                "it to finish before starting another"
            )
        steps = (*plan.steps, plan.target)
        save_chain(self.record, SavedChain(plan.game.game_id, steps))
        self._run(plan.game, steps)
        assert self.chain is not None
        return self.chain

    @property
    def target_name(self) -> str | None:
        """The mod a running chain installs, if any; e.g. ``flow.target_name``."""
        if self.chain is None or self.chain.finished:
            return None
        return self.chain.steps[-1].name

    @property
    def has_work(self) -> bool:
        """True when a tick has something to do or report; e.g. ``flow.has_work``."""
        return self.running or self.resume_error is not None

    @property
    def running(self) -> bool:
        """True while a chain has steps left; e.g. ``flow.running``."""
        return self.chain is not None and not self.chain.finished

    def advance(self) -> tuple[str, ...]:
        """Step the running chain; e.g. ``flow.advance()`` on a timer."""
        if self.resume_error is not None:
            error, self.resume_error = self.resume_error, None
            raise ValueError(error)
        if self.chain is None or self.chain_host is None or self.chain.finished:
            return ()
        if not self.lock.acquire(blocking=False):
            return ()
        try:
            return self._advance(self.chain, self.chain_host)
        finally:
            self.lock.release()

    def _advance(
        self, chain: RequirementChain, host: ServiceChainHost
    ) -> tuple[str, ...]:
        try:
            return chain.advance(host)
        finally:
            # Finished or failed (the chain marks both), nothing is left to resume.
            if chain.finished:
                clear_chain(self.record)
