"""Read requirement trees from Nexus' GraphQL API and order them."""

import unittest

from omamods.nexus_requirements import (
    GRAPHQL_URL,
    NexusRequirementsApi,
    parse_mod_requirements,
    resolve_requirements,
)
from tests.fakes import FakeNexusSite


def node(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "modId": 32203,
        "name": "Immersive Third Person",
        "gameId": 3333,
        "modRequirements": {
            "nexusRequirements": {
                "nodes": [
                    {
                        "modId": "4198",
                        "modName": "ArchiveXL",
                        "gameId": "3333",
                        "externalRequirement": False,
                        "url": "",
                        "notes": "Hard",
                    },
                    {
                        "modId": "0",
                        "modName": "Some Tool",
                        "gameId": "3333",
                        "externalRequirement": True,
                        "url": "https://x.example",
                        "notes": "",
                    },
                    {
                        "modId": "12",
                        "modName": "Other game",
                        "gameId": "1704",
                        "externalRequirement": False,
                        "url": "",
                        "notes": "",
                    },
                ]
            },
            "dlcRequirements": [{"gameExpansion": {"name": "Phantom Liberty"}}],
        },
    }
    return base | overrides


class ParseTests(unittest.TestCase):
    def test_splits_nexus_external_and_dlc(self) -> None:
        parsed = parse_mod_requirements(node())
        self.assertEqual(parsed.mod_id, 32203)
        self.assertEqual(
            [(r.mod_id, r.name) for r in parsed.nexus], [(4198, "ArchiveXL")]
        )
        self.assertEqual(
            parsed.external, ("Some Tool (https://x.example)", "Other game")
        )
        self.assertEqual(parsed.dlc, ("Phantom Liberty",))

    def test_bad_mod_id_names_the_value(self) -> None:
        with self.assertRaisesRegex(ValueError, r"modId='x'"):
            parse_mod_requirements(node(modId="x"))

    def test_graphql_errors_are_raised(self) -> None:
        class ErrorSite(FakeNexusSite):
            def post_json(self, url: str, api_key: str, body: object) -> object:
                return {"errors": [{"message": "Type mismatch"}]}

        api = NexusRequirementsApi(ErrorSite(), "k")
        with self.assertRaisesRegex(ValueError, "Type mismatch"):
            api.requirements("cyberpunk2077", (1,))


class ResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.site = FakeNexusSite()
        # Mirrors mod 32203: everything RED4ext-based needs RED4ext first.
        self.site.requirement_graph = {
            100: (4198, 107, 3518),
            4198: (2380,),
            3518: (107,),
        }
        self.api = NexusRequirementsApi(self.site, "k")

    def test_dependencies_come_before_their_users(self) -> None:
        tree = resolve_requirements(self.api, "cyberpunk2077", 100)
        self.assertEqual([r.mod_id for r in tree.order], [2380, 4198, 107, 3518])

    def test_each_level_is_one_query(self) -> None:
        resolve_requirements(self.api, "cyberpunk2077", 100)
        self.assertEqual(self.site.queries, [(100,), (107, 3518, 4198), (2380,)])

    def test_cycles_end(self) -> None:
        self.site.requirement_graph = {100: (1,), 1: (2,), 2: (1, 100)}
        tree = resolve_requirements(self.api, "cyberpunk2077", 100)
        self.assertEqual([r.mod_id for r in tree.order], [2, 1])

    def test_queries_go_to_graphql(self) -> None:
        sent: list[str] = []

        class RecordingSite(FakeNexusSite):
            def post_json(self, url: str, api_key: str, body: object) -> object:
                sent.append(url)
                return super().post_json(url, api_key, body)

        resolve_requirements(NexusRequirementsApi(RecordingSite(), "k"), "g", 5)
        self.assertEqual(sent, [GRAPHQL_URL])


if __name__ == "__main__":
    unittest.main()
