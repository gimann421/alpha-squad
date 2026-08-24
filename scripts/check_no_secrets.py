"""Guardrail against D35's failure mode: a real credential committed directly to a tracked
`.env.example`-style template file. Scans every git-tracked file whose name matches
`*.env.example` (or is `.env.example` itself, anywhere in the tree) for `KEY=value` lines where
the key looks secret-shaped (`_KEY`/`_SECRET`/`_TOKEN`/`_PASSWORD`/`_CREDENTIAL`, case-insensitive)
and the value is non-empty -- a template's whole point is that secret-shaped values stay blank;
any name-like/library/etc. line is left alone. Run via `make check-secrets` (also part of
`make lint`, so CI catches this the same way it catches everything else `make lint` covers).

Exits non-zero with the offending file:line printed (never the value itself) if it finds one.
"""

from __future__ import annotations

import re
import subprocess
import sys

SECRET_KEY_PATTERN = re.compile(r"(_KEY|_SECRET|_TOKEN|_PASSWORD|_CREDENTIAL)$", re.IGNORECASE)
ASSIGNMENT_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def _tracked_env_example_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.env.example", "**/.env.example"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def find_violations(path: str, lines: list[str]) -> list[str]:
    """Pure check, independently testable: which lines in this file look like a
    secret-shaped key given a real (non-empty) value."""
    violations = []
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ASSIGNMENT_PATTERN.match(stripped)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if SECRET_KEY_PATTERN.search(key) and value:
            violations.append(f"{path}:{lineno}: {key} has a non-empty value")
    return violations


def main() -> int:
    violations: list[str] = []
    for path in _tracked_env_example_files():
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as e:
            print(f"warning: could not read {path}: {e}", file=sys.stderr)
            continue
        violations.extend(find_violations(path, lines))

    if violations:
        print("Real-looking secret values found in a tracked *.env.example file:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nA .env.example is a tracked template -- real values here get committed and, in a "
            "public repo, published (see docs/DECISIONS.md D35). Use a local .env (gitignored) or "
            "this deployment's own env-var config instead, and leave the template value blank.",
            file=sys.stderr,
        )
        return 1

    print(f"check-secrets: clean ({len(_tracked_env_example_files())} template file(s) checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
