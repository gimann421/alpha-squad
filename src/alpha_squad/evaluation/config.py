"""Versioned configuration for the empirical-evaluation phase (docs/DECISIONS.md D54+).

PRODUCT_SPEC.md/ACCEPTANCE_CRITERIA.md already require every model be compared against
baselines and re-evaluated after model updates; this module is what makes that rerunnable
and dated rather than a one-off script. Every evaluation report generated in this phase
stamps its `EvaluationConfig` (as JSON) into the report, so a later re-run can be diffed
against exactly what assumptions and data windows produced an earlier number.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

EVALUATION_FRAMEWORK_VERSION = "2026.1"

# The real, verified data windows this phase's analyses can honestly claim to cover --
# checked against the live database before any report was written (see docs/DECISIONS.md
# D54), not assumed from what the pipeline is theoretically capable of. Every evaluation
# function in this package takes its own season range as an explicit argument; these are
# the honest defaults, not hardcoded limits enforced anywhere.
UNCERTAINTY_MODEL_SEASON_RANGE = (2021, 2025)  # uncertainty_predictions real coverage
EDGE_SEASON_RANGE = (2022, 2025)  # edge_snapshot real coverage
ROOKIE_CLASS_RANGE = (2019, 2025)  # rookie walk-forward classes with a real labeled outcome
ESTABLISHED_ML_SEASON_RANGE = (2020, 2025)  # ml_season_* evaluation_results real coverage
BASELINE_SEASON_RANGE = (2019, 2025)  # baseline_* evaluation_results real coverage


@dataclass
class EvaluationConfig:
    """Stamped into every generated report/JSON artifact. `random_seed` is None unless an
    analysis actually uses randomness (bootstrap CIs) -- most of this phase's analyses are
    deterministic historical replays, and a random seed on a deterministic analysis would
    be misleading provenance."""

    framework_version: str = EVALUATION_FRAMEWORK_VERSION
    ecr_type: str = "rsf"
    edge_model_version: str | None = None
    uncertainty_model_version: str | None = None
    season_start: int | None = None
    season_end: int | None = None
    random_seed: int | None = None
    notes: str = ""
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, default=str)
