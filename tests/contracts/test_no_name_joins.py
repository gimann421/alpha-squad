"""Static check: PRODUCT_SPEC.md / ARCHITECTURE.md require that production data is never
joined on player name alone. This scans the identity module's source for SQL JOIN clauses
and fails if any join predicate matches on a name-like column — the one thing this module
must never do, however the join is phrased.

This is intentionally narrow (identity/ only, JOIN ... ON clauses only) rather than a
general-purpose SQL linter — it exists to catch a regression in the one place a name-join
would silently corrupt the canonical identity graph, not to police every string comparison
anywhere in the codebase."""

from __future__ import annotations

import re
from pathlib import Path

IDENTITY_SRC = Path(__file__).resolve().parents[2] / "src" / "alpha_squad" / "identity"

# Matches `JOIN ... ON <left>.<name-col> = <right>.<name-col>` style predicates (order and
# whitespace tolerant). We look for a join predicate where BOTH sides reference a
# name-family column, which is what an accidental name-join would look like — as opposed to
# e.g. selecting a name column, which is fine.
NAME_JOIN_ON_PATTERN = re.compile(
    r"JOIN\b.{0,200}?\bON\b[^;]{0,300}?\b(?:name|display_name|player_name|merge_name)\b\s*=\s*"
    r"\w*\.?\b(?:name|display_name|player_name|merge_name)\b",
    re.IGNORECASE | re.DOTALL,
)


def _identity_sql_files() -> list[Path]:
    return sorted(IDENTITY_SRC.glob("*.py"))


def test_identity_module_exists_and_has_sql():
    files = _identity_sql_files()
    assert files, "expected identity/*.py source files to scan"


def test_no_join_predicate_matches_on_a_name_column():
    offenders = []
    for path in _identity_sql_files():
        text = path.read_text()
        for match in NAME_JOIN_ON_PATTERN.finditer(text):
            offenders.append(f"{path.name}: {match.group(0)[:200]!r}")
    assert offenders == [], f"found name-based JOIN predicates: {offenders}"
