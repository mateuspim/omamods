"""Keep the AyakaMods login cookie in the private config, beside the Nexus key.

[ayaka]
login_cookie = "347376,AbCdEf..."   # the browser's xf_user cookie value
"""

import json
from pathlib import Path
import re
import tomllib

from omamods.nexus_config import ConfigFiles, initialize_config

# XenForo's xf_user is "<user id>,<token>"; browsers store the comma as %2C.
COOKIE_SHAPE = re.compile(r"[1-9][0-9]*(?:,|%2C)[A-Za-z0-9_-]+")
COOKIE_LINE = re.compile(r"(?m)^login_cookie\s*=.*$")
AYAKA_TABLE = re.compile(r"(?m)^\[ayaka\]\s*$")


def normalize_cookie(text: str) -> str:
    """Accept the value or ``xf_user=value``; e.g. ``normalize_cookie('xf_user=1%2Cab')``."""
    value = text.strip().removeprefix("xf_user=").strip().strip('"')
    if not COOKIE_SHAPE.fullmatch(value):
        raise ValueError(
            "AyakaMods login cookie: expected the xf_user value, shaped like "
            "'347376%2CAbC...' (DevTools > Application > Cookies > ayakamods.com)"
        )
    # Sent back exactly as the browser stores it.
    return value


def read_login_cookie(source: str) -> str:
    """Read ayaka.login_cookie, or ''; e.g. ``read_login_cookie(config_text)``."""
    try:
        fields = tomllib.loads(source)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"config TOML: expected valid TOML: {error}") from error
    table = fields.get("ayaka", {})
    cookie = table.get("login_cookie", "") if isinstance(table, dict) else None
    if not isinstance(cookie, str):
        raise ValueError(f"ayaka.login_cookie={cookie!r}: expected a string")
    return cookie


def with_login_cookie(source: str, cookie: str) -> str:
    """Set ayaka.login_cookie in TOML text; e.g. ``with_login_cookie(text, '1,ab')``."""
    line = f"login_cookie = {json.dumps(normalize_cookie(cookie))}"
    if COOKIE_LINE.search(source):
        return COOKIE_LINE.sub(lambda _: line, source, count=1)
    if AYAKA_TABLE.search(source):
        return AYAKA_TABLE.sub(lambda _: f"[ayaka]\n{line}", source, count=1)
    # Appended last: a new table header also ends any [[mods]] entry above it.
    return f"{source.rstrip()}\n\n[ayaka]\n{line}\n"


def load_login_cookie(path: Path, files: ConfigFiles) -> str:
    """Read the saved cookie, or '' without a config; e.g. ``load_login_cookie(p, files)``."""
    try:
        return read_login_cookie(files.read_text(path))
    except FileNotFoundError:
        return ""


def save_login_cookie(
    path: Path, storage_root: Path, cookie: str, files: ConfigFiles
) -> None:
    """Store the cookie privately; e.g. ``save_login_cookie(path, root, value, files)``."""
    try:
        source = files.read_text(path)
    except FileNotFoundError:
        initialize_config(path, storage_root, files)
        source = files.read_text(path)
    updated = with_login_cookie(source, cookie)
    read_login_cookie(updated)
    files.replace_private(path, updated)
