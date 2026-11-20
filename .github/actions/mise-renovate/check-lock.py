"""Fail unless mise.lock pins every mise.toml tool, at its exact version, for every locked platform.

mise checks a download against mise.lock only when an entry exists. A tool or platform missing from the
lock, or a lock left behind by a mise.toml bump, would install unverified or fail later.
"""

import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

# The algorithms mise.lock documents, each at its full digest length.
CHECKSUM = re.compile(r"(?:sha256|blake3):[0-9a-f]{64}|sha512:[0-9a-f]{128}")


def pin_of(spec: object) -> str | None:
    """The version mise.toml requests for one tool, in either the string or the table form."""
    if isinstance(spec, dict):
        spec = spec.get("version")
    return spec if isinstance(spec, str) and spec else None


def lock_key(name: str, locked: dict) -> str:
    """The key mise.lock files a tool under: as written, or with a backend prefix such as `core:` dropped."""
    if name in locked or ":" not in name:
        return name
    return name.split(":", 1)[1]


def is_https(url: object) -> bool:
    parts = urlsplit(str(url))
    return parts.scheme == "https" and bool(parts.hostname)


def problems(mise: dict, lock: dict) -> list[str]:
    """Return why the lock does not cover mise.toml; empty means it does."""
    platforms = mise.get("settings", {}).get("lockfile_platforms")
    if not platforms:
        return ["mise.toml sets no [settings] lockfile_platforms to check against"]
    tools = mise.get("tools", {})
    if not tools:
        return ["mise.toml declares no [tools]"]
    locked = lock.get("tools", {})
    expected = {lock_key(name, locked) for name in tools}
    found = [
        f"mise.lock has {name}, which mise.toml no longer declares"
        for name in locked
        if name not in expected
    ]
    for name, spec in tools.items():
        pin = pin_of(spec)
        entries = locked.get(lock_key(name, locked), [])
        if pin is None:
            found.append(f"{name} has no exact version in mise.toml")
            continue
        if len(entries) != 1:
            found.append(f"mise.lock has {len(entries)} entries for {name}, expected 1")
            continue
        (entry,) = entries
        if entry.get("version") != pin:
            found.append(
                f"mise.lock locks {name} at {entry.get('version')}, mise.toml pins {pin}"
            )
        for platform in platforms:
            artifact = entry.get(f"platforms.{platform}", {})
            if not is_https(artifact.get("url", "")):
                found.append(f"{name} has no https URL for {platform}")
            if not CHECKSUM.fullmatch(str(artifact.get("checksum", ""))):
                found.append(f"{name} has no checksum for {platform}")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: check-lock.py <mise.toml> <mise.lock>", file=sys.stderr)
        return 2
    try:
        mise, lock = (
            tomllib.loads(Path(arg).read_text(encoding="utf-8")) for arg in argv[1:]
        )
    except (OSError, ValueError) as err:
        print(f"::error::cannot read mise.toml and mise.lock: {err}")
        return 1
    found = problems(mise, lock)
    for problem in found:
        print(f"::error::{problem}")
    if found:
        return 1
    print(f"mise.lock pins all {len(mise['tools'])} tools in {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
