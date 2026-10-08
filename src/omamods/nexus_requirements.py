"""Read a mod's requirements from Nexus' v2 GraphQL API and order them.

The v1 API has no requirements; the mod page's "Requirements" section is
served by v2, which also lists ones the description leaves out (mod 32203
needs redscript but its text never says so).
"""

from dataclasses import dataclass

from omamods.nexus_api import NexusTransport

GRAPHQL_URL = "https://api.nexusmods.com/v2/graphql"
REQUIREMENTS_QUERY = """
query($ids: [CompositeDomainWithIdInput!]!) {
  legacyModsByDomain(ids: $ids) {
    nodes {
      modId name gameId
      modRequirements {
        nexusRequirements { nodes { modId modName gameId externalRequirement url notes } }
        dlcRequirements { gameExpansion { name } }
      }
    }
  }
}
"""
# Nexus caps how many mods one query may name; trees are far smaller.
MAX_REQUIRED_MODS = 60


@dataclass(frozen=True)
class NexusRequirement:
    """A required mod on the same game's Nexus pages."""

    mod_id: int
    name: str
    notes: str


@dataclass(frozen=True)
class ModRequirements:
    """What one mod's Requirements section lists."""

    mod_id: int
    name: str
    nexus: tuple[NexusRequirement, ...]
    # Off-site tools and other games' mods, which OmaMods cannot fetch.
    external: tuple[str, ...]
    dlc: tuple[str, ...]


@dataclass(frozen=True)
class RequirementTree:
    """Every mod a mod needs, each listed after the mods it needs itself."""

    order: tuple[NexusRequirement, ...]
    external: tuple[str, ...]
    dlc: tuple[str, ...]


def _field(value: object, key: str) -> object:
    if not isinstance(value, dict) or key not in value:
        raise ValueError(f"Nexus GraphQL value={value!r}: expected a {key!r} field")
    return value[key]


def _nodes(value: object, key: str) -> list[object]:
    nodes = _field(_field(value, key), "nodes")
    if not isinstance(nodes, list):
        raise ValueError(f"Nexus GraphQL {key}={nodes!r}: expected a node list")
    return nodes


def _text(value: object, key: str) -> str:
    field = value.get(key) if isinstance(value, dict) else None
    return field if isinstance(field, str) else ""


def _mod_id(value: object) -> int:
    # v2 sends required mod IDs as strings and the mod's own as a number.
    raw = _field(value, "modId")
    text = str(raw)
    if type(raw) is bool or not text.isdecimal() or int(text) <= 0:
        raise ValueError(f"Nexus modId={raw!r}: expected a positive mod ID")
    return int(text)


def _is_external(node: object, game_id: str) -> bool:
    return bool(_field(node, "externalRequirement")) or str(
        _field(node, "gameId")
    ) != str(game_id)


def _external_name(node: object) -> str:
    url = _text(node, "url")
    return f"{_text(node, 'modName')} ({url})" if url else _text(node, "modName")


def _dlc_names(requirements: object) -> tuple[str, ...]:
    entries = _field(requirements, "dlcRequirements")
    if not isinstance(entries, list):
        raise ValueError(f"Nexus dlcRequirements={entries!r}: expected a list")
    return tuple(_text(_field(entry, "gameExpansion"), "name") for entry in entries)


def parse_mod_requirements(node: object) -> ModRequirements:
    """Validate one mod node; e.g. ``parse_mod_requirements(response_node)``."""
    requirements = _field(node, "modRequirements")
    listed = _nodes(requirements, "nexusRequirements")
    game_id = str(_field(node, "gameId"))
    nexus = tuple(
        NexusRequirement(_mod_id(item), _text(item, "modName"), _text(item, "notes"))
        for item in listed
        if not _is_external(item, game_id)
    )
    external = tuple(_external_name(i) for i in listed if _is_external(i, game_id))
    name = _text(node, "name")
    return ModRequirements(
        _mod_id(node), name, nexus, external, _dlc_names(requirements)
    )


def _response_nodes(response: object) -> list[object]:
    errors = response.get("errors") if isinstance(response, dict) else None
    if errors:
        raise ValueError(f"Nexus GraphQL errors={errors!r}: expected none")
    return _nodes(_field(response, "data"), "legacyModsByDomain")


class NexusRequirementsApi:
    """Ask Nexus what mods need; e.g. ``NexusRequirementsApi(http, key)``."""

    def __init__(self, transport: NexusTransport, api_key: str) -> None:
        self.transport = transport
        self.api_key = api_key

    def requirements(
        self, domain: str, mod_ids: tuple[int, ...]
    ) -> tuple[ModRequirements, ...]:
        """Read several mods at once; e.g. ``api.requirements('cyberpunk2077', (1,))``."""
        ids = [{"gameDomain": domain, "modId": mod_id} for mod_id in mod_ids]
        body = {"query": REQUIREMENTS_QUERY, "variables": {"ids": ids}}
        response = self.transport.post_json(GRAPHQL_URL, self.api_key, body)
        return tuple(parse_mod_requirements(n) for n in _response_nodes(response))


def _fetch_graph(
    api: NexusRequirementsApi, domain: str, mod_id: int
) -> dict[int, ModRequirements]:
    graph: dict[int, ModRequirements] = {}
    wanted: tuple[int, ...] = (mod_id,)
    while wanted:
        if len(graph) + len(wanted) > MAX_REQUIRED_MODS:
            raise ValueError(
                f"mod {mod_id} requirements={len(graph) + len(wanted)}: expected "
                f"at most {MAX_REQUIRED_MODS} mods"
            )
        found = api.requirements(domain, wanted)
        graph.update((mods.mod_id, mods) for mods in found)
        listed = (r.mod_id for mods in found for r in mods.nexus)
        wanted = tuple(sorted({i for i in listed if i not in graph}))
    return graph


def _dependency_order(
    graph: dict[int, ModRequirements], mod_id: int
) -> tuple[NexusRequirement, ...]:
    order: list[NexusRequirement] = []
    seen = {mod_id}

    def visit(requirement: NexusRequirement) -> None:
        seen.add(requirement.mod_id)
        node = graph.get(requirement.mod_id)
        for needed in node.nexus if node else ():
            if needed.mod_id not in seen:
                visit(needed)
        order.append(requirement)

    for requirement in graph[mod_id].nexus:
        if requirement.mod_id not in seen:
            visit(requirement)
    return tuple(order)


def resolve_requirements(
    api: NexusRequirementsApi, domain: str, mod_id: int
) -> RequirementTree:
    """Walk the whole tree; e.g. ``resolve_requirements(api, 'cyberpunk2077', 32203)``."""
    graph = _fetch_graph(api, domain, mod_id)
    if mod_id not in graph:
        raise ValueError(f"Nexus {domain} mod={mod_id}: expected it in the response")
    external = sorted({name for mods in graph.values() for name in mods.external})
    dlc = sorted({name for mods in graph.values() for name in mods.dlc if name})
    order = _dependency_order(graph, mod_id)
    return RequirementTree(order, tuple(external), tuple(dlc))
