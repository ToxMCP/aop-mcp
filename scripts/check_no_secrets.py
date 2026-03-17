#!/usr/bin/env python3
"""Fail fast on tracked env files and committed CompTox credentials."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_TRACKED_ENV_FILES = {".env.example"}
COMPTOX_KEY_PATTERNS = (
    re.compile(r"^\s*AOP_MCP_COMPTOX_API_KEY\s*=\s*(?P<value>.+?)\s*$"),
    re.compile(r"^\s*COMPTOX_API_KEY\s*=\s*(?P<value>.+?)\s*$"),
)
PLACEHOLDER_PREFIXES = (
    "replace-",
    "your-",
    "example-",
    "changeme",
    "dummy",
    "test-",
)


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    return [ROOT / line for line in output.splitlines() if line.strip()]


def is_placeholder(value: str) -> bool:
    normalized = value.strip().strip("\"'").lower()
    if not normalized:
        return True
    if normalized.startswith("${") or normalized.startswith("<"):
        return True
    return any(normalized.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES)


def main() -> int:
    violations: list[str] = []

    for path in tracked_files():
        relpath = path.relative_to(ROOT).as_posix()

        if path.name.startswith(".env") and path.name not in ALLOWED_TRACKED_ENV_FILES:
            violations.append(f"Tracked env file is not allowed: {relpath}")

        if not path.is_file():
            continue

        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        for lineno, line in enumerate(lines, start=1):
            for pattern in COMPTOX_KEY_PATTERNS:
                match = pattern.match(line)
                if match and not is_placeholder(match.group("value")):
                    violations.append(f"Committed CompTox key-like assignment in {relpath}:{lineno}")

    if violations:
        print("Secret hygiene check failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1

    print("Secret hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
