"""Top-level orchestration for the as-of feature pipeline: games -> player_week_stats ->
player_week_features -> player_season_stats, in that dependency order."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from alpha_squad.config.settings import Settings, get_settings
from alpha_squad.features.games import build_games_table
from alpha_squad.features.panel import build_player_week_features
from alpha_squad.features.player import build_player_week_stats
from alpha_squad.features.season_aggregate import build_player_season_stats


@dataclass
class FeatureBuildReport:
    games_inserted: int = 0
    player_week_stats_upserted: int = 0
    player_week_features_upserted: int = 0
    player_season_stats_upserted: int = 0


def build_features(
    con: duckdb.DuckDBPyConnection, settings: Settings | None, seasons: list[int]
) -> FeatureBuildReport:
    settings = settings or get_settings()
    report = FeatureBuildReport()
    report.games_inserted = build_games_table(con, settings, seasons)
    report.player_week_stats_upserted = build_player_week_stats(con, settings, seasons)
    report.player_week_features_upserted = build_player_week_features(con)
    report.player_season_stats_upserted = build_player_season_stats(con, seasons)
    return report
