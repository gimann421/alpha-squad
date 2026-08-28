"""Top-level orchestration for the as-of feature pipeline: games -> player_week_stats ->
player_week_features -> player_season_stats, the team-environment signal (team_week_stats ->
team_week_features -> attached onto player_week_features), combine results, and the rookie
feature table (which depends on player_season_stats, team_week_stats, and combine_results
all being built first) — in that dependency order."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from alpha_squad.config.settings import Settings, get_settings
from alpha_squad.features.combine import build_combine_results
from alpha_squad.features.games import build_games_table
from alpha_squad.features.kicking_defense import build_kicking_and_defense
from alpha_squad.features.panel import build_player_week_features
from alpha_squad.features.player import build_player_week_stats
from alpha_squad.features.rookie import build_rookie_features
from alpha_squad.features.season_aggregate import build_player_season_stats
from alpha_squad.features.team import (
    attach_team_features_to_player_panel,
    build_team_week_features,
    build_team_week_stats,
)


@dataclass
class FeatureBuildReport:
    games_inserted: int = 0
    player_week_stats_upserted: int = 0
    player_week_features_upserted: int = 0
    player_season_stats_upserted: int = 0
    team_week_stats_upserted: int = 0
    team_week_features_upserted: int = 0
    player_panel_team_attached: int = 0
    combine_results_upserted: int = 0
    rookie_features_upserted: int = 0
    kicker_week_rows_scored: int = 0
    dst_entities_created: int = 0
    dst_week_rows: int = 0


def build_features(
    con: duckdb.DuckDBPyConnection, settings: Settings | None, seasons: list[int]
) -> FeatureBuildReport:
    settings = settings or get_settings()
    report = FeatureBuildReport()
    report.games_inserted = build_games_table(con, settings, seasons)
    report.player_week_stats_upserted = build_player_week_stats(con, settings, seasons)
    report.player_week_features_upserted = build_player_week_features(con)
    report.team_week_stats_upserted = build_team_week_stats(con, settings, seasons)

    # K/DEF scoring (D57) sits here deliberately: it needs `team_week_stats` (defensive
    # counting stats) and `team_week_points` (points allowed) to already exist, and it writes
    # into `player_week_stats`, so it must run BEFORE the season aggregate rolls those weekly
    # rows up. Running it after would leave every kicker's and defense's season total at the
    # stale value the aggregate had already computed.
    kd = build_kicking_and_defense(con, settings, seasons)
    report.kicker_week_rows_scored = kd["kicker_week_rows_scored"]
    report.dst_entities_created = kd["dst_entities_created"]
    report.dst_week_rows = kd["dst_week_rows"]

    report.player_season_stats_upserted = build_player_season_stats(con, seasons)
    report.team_week_features_upserted = build_team_week_features(con)
    report.player_panel_team_attached = attach_team_features_to_player_panel(con)
    report.combine_results_upserted = build_combine_results(con, settings)
    report.rookie_features_upserted = build_rookie_features(con)
    return report
