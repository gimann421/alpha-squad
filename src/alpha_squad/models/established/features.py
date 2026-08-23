"""Feature-set definitions for established-player ML, built on top of M3's
player_week_features panel (extended in M5 with team-environment columns — see
features/team.py). Every column here is already leakage-safe by construction (SQL window
frames excluding the current/future row); this module just groups them into named sets so
the opportunity-only and team-environment-only models can be isolated for interpretability
(ARCHITECTURE.md §5 lists "opportunity" and "team environment" as separate model
components)."""

from __future__ import annotations

OPPORTUNITY_FEATURES = [
    "targets_avg_last3",
    "carries_avg_last3",
    "receptions_avg_last3",
    "target_share_avg_last3",
    "snap_pct_avg_last3",
]

TEAM_FEATURES = [
    "team_plays_avg_last3",
    "team_pass_rate_avg_last3",
    "team_epa_avg_last3",
]

HISTORICAL_FEATURES = [
    "games_played_prior",
    "fp_ppr_avg_last3",
    "fp_ppr_avg_season_to_date",
]

FULL_FEATURES = HISTORICAL_FEATURES + OPPORTUNITY_FEATURES + TEAM_FEATURES

TARGET_COLUMN = "target_fantasy_points_ppr"
FEATURE_VERSION = "established_ml_v1"
POSITIONS = ("QB", "RB", "WR", "TE")
