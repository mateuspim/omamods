"""Keep the third-party YAML parser behind a project-owned boundary."""

from typing import Protocol

import yaml
from yaml.nodes import MappingNode


class ManifestDecoder(Protocol):
    """Decode a manifest without coupling validation to a YAML library."""

    def decode(self, source: str) -> object:
        """Decode text; for example, ``decoder.decode('id: dawnwalker')``."""
        ...


class _UniqueLoader(yaml.SafeLoader):
    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[object, object]:
        result: dict[object, object] = {}
        for key_node, value_node in node.value:
            key: object = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ValueError(f"YAML key {key!r}: expected a unique string key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


class SafeYamlDecoder:
    """Reject executable YAML tags and ambiguous duplicate fields."""

    def decode(self, source: str) -> object:
        """Decode safely; for example, ``SafeYamlDecoder().decode('id: demo')``."""
        try:
            return yaml.load(source, Loader=_UniqueLoader)
        except yaml.YAMLError as error:
            raise ValueError(
                f"YAML {source!r}: expected valid safe YAML: {error}"
            ) from error
