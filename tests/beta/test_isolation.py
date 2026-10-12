"""W16: the experimental beta cannot alter the frozen 2026 validation.

Four separate guarantees:

1. nothing on the research / validation path imports the beta code;
2. every file on W10's frozen code path (W14 gate G2's list) is byte-identical to W10's results
   commit, so the beta cannot have changed the model it serves;
3. the committed W10-W15 result artifacts are the ones the reports cite (pinned sha256);
4. the beta runner opens every database read-only and writes only an in-memory scratch database.
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from scripts.research.w14_validity_gates import W10_COMMIT, W10_PATH

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
BETA_RUNNER = ROOT / "scripts/beta/weekly_board.py"

#: sha256 of the frozen weekly artifacts as committed by W10-W15 (W15 cites w15's `2a423650…`).
FROZEN_ARTIFACTS = {
    "reports/weekly/w10_results.json": "7963324aea45af2139b6da221e7ea3cd8419a2576f7ceffdab9eb43bb79ea1b5",
    "reports/weekly/w14_results.json": "3dbb7f1276986e8e490b9a89306eecadd2c4ef3a58dd5e5a42fe90a5e79d28a9",
    "reports/weekly/w15_results.json": "2a423650662adb0203ffbf4a8c1039ba81d5652f6a2d01e560e35c79544a6ac0",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_no_research_or_production_module_imports_the_beta():
    roots = [ROOT / "scripts/research", ROOT / "src/alpha_squad"]
    offenders = []
    for root in roots:
        for f in root.rglob("*.py"):
            if "beta" in f.relative_to(ROOT).parts:
                continue
            if any(m.startswith(("alpha_squad.beta", "scripts.beta")) for m in _imports(f)):
                offenders.append(str(f.relative_to(ROOT)))
    assert offenders == []


def test_w10_frozen_code_path_unchanged_since_w10_commit():
    try:
        subprocess.run(
            ["git", "cat-file", "-e", W10_COMMIT], cwd=ROOT, check=True, capture_output=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip(f"git history with {W10_COMMIT} not available")
    diff = subprocess.run(
        ["git", "diff", "--stat", W10_COMMIT, "--", *W10_PATH],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert diff == "", f"W10 path changed since {W10_COMMIT}:\n{diff}"


@pytest.mark.parametrize("rel,sha", sorted(FROZEN_ARTIFACTS.items()))
def test_frozen_validation_artifacts_unchanged(rel, sha):
    assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha


def test_beta_runner_opens_databases_read_only():
    src = BETA_RUNNER.read_text()
    calls = re.findall(r"duckdb\.connect\(([^)]*)\)", src)
    assert calls, "expected the runner to open databases"
    for args in calls:
        # In-memory scratch (no path) or an explicit read-only connection; nothing else.
        assert args.strip() == "" or "read_only=True" in args, args


def test_beta_runner_fits_through_frozen_functions_only():
    """The runner fits no model of its own: every fit goes through W10's
    `arms.train_with_extra_features`, with either no extra features (production's model exactly)
    or W10's frozen seven, so neither model specification can drift. Three call sites: the
    control arm, the W10 arm, and the W10 reference fit the fidelity check compares against."""
    src = BETA_RUNNER.read_text()
    assert "CatBoostRegressor" not in src and ".fit(" not in src
    calls = [
        node
        for node in ast.walk(ast.parse(src))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "train_with_extra_features"
    ]
    assert len(calls) == 3
    for call in calls:
        extra_cols = ast.unparse(call.args[2])
        assert extra_cols in ("[]", "list(mech.DURABLE_FEATURES)"), extra_cols


def test_missing_prior_season_uses_w10s_own_no_prior_values():
    from alpha_squad.evaluation.weekly import mechanisms as mech
    from scripts.beta.weekly_board import _complete_durable

    dur = pd.DataFrame(
        [
            {
                "player_id": "a",
                "season": 2026,
                **mech.durable_features(
                    [
                        {
                            "week": 1,
                            "ppr": 10.0,
                            "targets": 5,
                            "carries": 0,
                            "target_share": 0.2,
                            "snap": 0.8,
                        }
                    ],
                    12,
                ),
            }
        ]
    )
    out = _complete_durable(dur, 2026, ["a", "rookie"]).set_index("player_id")
    assert out.loc["a", "has_prior"] == 1.0
    assert out.loc["rookie", "has_prior"] == 0.0  # not NaN: W10's own "no prior season" value
    assert pd.isna(out.loc["rookie", "prior_ppg"])
    assert len(_complete_durable(dur, 2026, ["a"])) == 1
