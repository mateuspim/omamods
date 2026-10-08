"""Walk a requirement chain against a named fake host."""

import unittest

from omamods.nexus_api import NexusFile
from omamods.requirement_chain import ChainStep, RequirementChain

RED4EXT = ChainStep(2380, "RED4ext", (NexusFile(1, "r.zip", "MAIN", 0),))
ARCHIVEXL = ChainStep(4198, "ArchiveXL", (NexusFile(2, "a.zip", "MAIN", 0),))
TARGET = ChainStep(100, "Third Person", (NexusFile(3, "t.zip", "MAIN", 0),), True)


class FakeChainHost:
    """Track installs and downloads; ``instant`` models a Premium account."""

    def __init__(self, instant: bool = False, failing: int | None = None) -> None:
        self.instant = instant
        self.failing = failing
        self.installed: set[int] = set()
        self.staged: set[int] = set()
        self.requests: list[int] = []

    def step_installed(self, step: ChainStep) -> bool:
        return step.mod_id in self.installed

    def step_staged(self, step: ChainStep) -> bool:
        return step.mod_id in self.staged

    def install_step(self, step: ChainStep) -> int:
        if step.mod_id == self.failing:
            raise ValueError(f"mod={step.mod_id}: expected an installable archive")
        self.installed.add(step.mod_id)
        return 2

    def request_step(self, step: ChainStep) -> bool:
        self.requests.append(step.mod_id)
        if self.instant:
            self.staged.add(step.mod_id)
        return self.instant


class ChainTests(unittest.TestCase):
    def test_premium_installs_everything_in_one_tick(self) -> None:
        host = FakeChainHost(instant=True)
        chain = RequirementChain((RED4EXT, ARCHIVEXL, TARGET))
        messages = chain.advance(host)
        self.assertEqual(host.requests, [2380, 4198, 100])
        self.assertTrue(chain.finished)
        self.assertEqual(messages[-1], "Third Person: it and its requirements are in")

    def test_browser_downloads_are_requested_one_at_a_time(self) -> None:
        host = FakeChainHost()
        host.staged.add(100)
        chain = RequirementChain((RED4EXT, ARCHIVEXL, TARGET))
        self.assertEqual(chain.advance(host), ("RED4ext: waiting for its download",))
        self.assertEqual(chain.advance(host), ())
        host.staged.add(2380)
        self.assertEqual(
            chain.advance(host),
            ("RED4ext: installed 2 files", "ArchiveXL: waiting for its download"),
        )
        self.assertEqual(host.requests, [2380, 4198])
        self.assertFalse(chain.finished)

    def test_present_requirements_are_skipped(self) -> None:
        host = FakeChainHost(instant=True)
        host.installed.add(2380)
        RequirementChain((RED4EXT, ARCHIVEXL, TARGET)).advance(host)
        self.assertEqual(host.requests, [4198, 100])

    def test_a_failed_install_stops_the_chain(self) -> None:
        host = FakeChainHost(instant=True, failing=2380)
        chain = RequirementChain((RED4EXT, TARGET))
        with self.assertRaisesRegex(ValueError, "mod=2380"):
            chain.advance(host)
        self.assertTrue(chain.finished)
        self.assertNotIn(100, host.requests)


if __name__ == "__main__":
    unittest.main()
