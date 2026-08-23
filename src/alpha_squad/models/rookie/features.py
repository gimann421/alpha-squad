"""Feature-set definition for rookie/prospect modeling. Separate from
established/features.py by design (PRODUCT_SPEC.md: "Rookies are a separate model because
they lack NFL production") — a rookie has no player_week_features history to draw lag
features from, so this operates on draft capital + combine + landing spot + college
production (D38) instead."""

from __future__ import annotations

FEATURES = [
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
    "college_usage_overall",
    "college_usage_pass",
    "college_usage_rush",
]
REGRESSION_TARGET = "rookie_year_ppr_points"
CLASSIFICATION_TARGET = "breakout_top24"
FEATURE_VERSION = "rookie_features_v2"  # v1 -> v2 (D38): +college_usage_overall/pass/rush
POSITIONS = ("QB", "RB", "WR", "TE")

# Undrafted free agents have draft_round/draft_pick = NULL. Rather than imputing them to 0
# (which would look like "drafted 0th overall" -- nonsensical), impute to one round/pick
# past the last real draft slot, i.e. a deliberately worse-than-Mr.-Irrelevant value.
UNDRAFTED_ROUND_FALLBACK = 8.0
UNDRAFTED_PICK_FALLBACK = 300.0
