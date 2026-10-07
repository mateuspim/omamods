"""Parse the text KeyValues subset used by Steam's local discovery files."""

from dataclasses import dataclass
import re

type KeyValues = dict[str, str | KeyValues]


def _tokenize(source: str) -> tuple[str, ...]:
    pattern = re.compile(r'\s+|//[^\n]*|"(?:\\.|[^"\\])*"|[{}]|[^\s{}"]+')
    position = 0
    tokens: list[str] = []
    while position < len(source):
        match = pattern.match(source, position)
        if match is None:
            raise ValueError(
                f"KeyValues {source[position:position + 40]!r}: expected a closed quoted string"
            )
        token = match.group()
        position = match.end()
        if not token.isspace() and not token.startswith("//"):
            tokens.append(token)
    return tuple(tokens)


def _unquote(token: str) -> str:
    if not token.startswith('"'):
        return token
    return re.sub(r'\\(["\\])', r"\1", token[1:-1])


@dataclass
class _Cursor:
    tokens: tuple[str, ...]
    position: int = 0

    def take(self) -> str:
        if self.position == len(self.tokens):
            raise ValueError(
                "KeyValues '<end>': expected a key, value, or closing brace"
            )
        token = self.tokens[self.position]
        self.position += 1
        return token

    def block(self, depth: int = 0) -> KeyValues:
        if depth > 16:
            raise ValueError(
                f"KeyValues depth={depth}: expected at most 16 nested blocks"
            )
        result: KeyValues = {}
        while self.position < len(self.tokens):
            key = self.take()
            if key == "}" and depth:
                return result
            if key in ("{", "}"):
                raise ValueError(f"KeyValues key={key!r}: expected a string key")
            self._pair(result, _unquote(key), depth)
        if depth:
            raise ValueError("KeyValues '<end>': expected a closing brace")
        return result

    def _pair(self, result: KeyValues, key: str, depth: int) -> None:
        if key in result:
            raise ValueError(f"KeyValues key={key!r}: expected a unique key")
        value = self.take()
        if value == "}":
            raise ValueError(
                f"KeyValues value={value!r}: expected a string or opening brace"
            )
        result[key] = self.block(depth + 1) if value == "{" else _unquote(value)


def parse_keyvalues(source: str) -> KeyValues:
    """Parse Steam text; for example, ``parse_keyvalues('"buildid" "123"')``."""
    return _Cursor(_tokenize(source.lstrip("\ufeff"))).block()


def keyvalues_block(document: KeyValues, key: str) -> KeyValues:
    """Require a named block; for example, ``keyvalues_block(parsed, 'AppState')``."""
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key}={value!r}: expected a KeyValues block")
    return value
