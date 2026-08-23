"""Feature-set definition for rookie/prospect modeling. Separate from
established/features.py by design (PRODUCT_SPEC.md: "Rookies are a separate model because
they lack NFL production") — a rookie has no player_week_features history to draw lag
features from, so this operates on draft capital + combine + landing spot + college
production (D38) instead."""

from __future__ import annotations

# The pre-D38 feature set: draft capital + combine + landing spot, all cleanly identity-linked
# with no college production (D20). Kept as a named list rather than deleted so the college
# features can be ablated against a real baseline on identical walk-forward folds -- otherwise
# "did college production help?" is unanswerable, since evaluation_results is keyed on
# (model_name, season, position) and a second training run would silently overwrite the first.
FEATURES_V1 = [
    "draft_round",
    "draft_pick",
    "forty",
    "bench",
    "vertical",
    "broad_jump",
    "cone",
    "shuttle",
    "height",
    "weight",
    "landing_team_prior_pass_rate",
    "landing_team_prior_plays",
]

# College production via CFBD, espn_id-bridged (D38).
COLLEGE_FEATURES = [
    "college_usage_overall",
    "college_usage_pass",
    "college_usage_rush",
]

# The candidate feature set the D39 ablation evaluated. NOT the production set: measured
# against the baseline over identical walk-forward folds it was neutral-to-slightly-worse on
# every metric that matters (see reports/rookie_college_production_ablation.md), so
# `FEATURES` below stays at the baseline. Kept wired up, not deleted, so the experiment is
# re-runnable the moment there's a reason to revisit it -- better CFBD coverage for older
# draft classes, or a college feature with more signal than raw usage share.
FEATURES_WITH_COLLEGE = FEATURES_V1 + COLLEGE_FEATURES

# Production feature set. Reverted from FEATURES_WITH_COLLEGE to the baseline in D39 on the
# ablation's measured result, per a decision rule fixed before the numbers were seen.
FEATURES = FEATURES_V1
REGRESSION_TARGET = "rookie_year_ppr_points"
CLASSIFICATION_TARGET = "breakout_top24"
# Back to v1 in D39: the production model trains on the baseline feature set again, so
# claiming v2 here would misdescribe every model registered and every prediction written.
FEATURE_VERSION = "rookie_features_v1"
# The ablation arm's version, kept distinct so both arms' rows coexist in model_registry /
# rookie_predictions instead of one silently overwriting the other.
COLLEGE_FEATURE_VERSION = "rookie_features_v2_college"
POSITIONS = ("QB", "RB", "WR", "TE")

# Undrafted free agents have draft_round/draft_pick = NULL. Rather than imputing them to 0
# (which would look like "drafted 0th overall" -- nonsensical), impute to one round/pick
# past the last real draft slot, i.e. a deliberately worse-than-Mr.-Irrelevant value.
UNDRAFTED_ROUND_FALLBACK = 8.0
UNDRAFTED_PICK_FALLBACK = 300.0
