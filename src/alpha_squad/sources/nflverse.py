"""nflverse adapter. No auth required. Verified reachable 2026-08-20 via GitHub release
assets (following redirects through release-assets.githubusercontent.com).

Note: the weekly-stats release tag is `stats_player` (nflverse's current naming). The older
`player_stats` tag and any `stats_player_season_*`/`stats_team_season_*` files do not exist —
confirmed 404. Season-level aggregates are derived from weekly data downstream instead,
which is also the correct choice for as-of integrity (a mid-season "season total" published
before the season ends would be a leakage hazard if it existed)."""

from __future__ import annotations

from alpha_squad.sources.file_release import DatasetSpec, FileReleaseSourceAdapter

_BASE = "https://github.com/nflverse/nflverse-data/releases/download"


class NflverseSource(FileReleaseSourceAdapter):
    name = "nflverse"
    datasets = {
        "players": DatasetSpec("players", f"{_BASE}/players/players.parquet", "parquet"),
        "stats_player_week": DatasetSpec(
            "stats_player_week",
            f"{_BASE}/stats_player/stats_player_week_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2024,
        ),
        "stats_team_week": DatasetSpec(
            "stats_team_week",
            f"{_BASE}/stats_team/stats_team_week_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2025,
        ),
        "rosters": DatasetSpec(
            "rosters",
            f"{_BASE}/rosters/roster_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2026,
        ),
        "weekly_rosters": DatasetSpec(
            "weekly_rosters",
            f"{_BASE}/weekly_rosters/roster_weekly_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2024,
        ),
        "depth_charts": DatasetSpec(
            "depth_charts",
            f"{_BASE}/depth_charts/depth_charts_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2026,
        ),
        "injuries": DatasetSpec(
            "injuries",
            f"{_BASE}/injuries/injuries_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2024,
        ),
        "snap_counts": DatasetSpec(
            "snap_counts",
            f"{_BASE}/snap_counts/snap_counts_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2024,
        ),
        "draft_picks": DatasetSpec(
            "draft_picks", f"{_BASE}/draft_picks/draft_picks.parquet", "parquet"
        ),
        "combine": DatasetSpec("combine", f"{_BASE}/combine/combine.parquet", "parquet"),
        "pbp": DatasetSpec(
            "pbp",
            f"{_BASE}/pbp/play_by_play_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2024,
        ),
        "ftn_charting": DatasetSpec(
            "ftn_charting",
            f"{_BASE}/ftn_charting/ftn_charting_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2024,
        ),
        "ngs_passing": DatasetSpec(
            "ngs_passing", f"{_BASE}/nextgen_stats/ngs_passing.parquet", "parquet"
        ),
        "ngs_rushing": DatasetSpec(
            "ngs_rushing", f"{_BASE}/nextgen_stats/ngs_rushing.parquet", "parquet"
        ),
        "ngs_receiving": DatasetSpec(
            "ngs_receiving", f"{_BASE}/nextgen_stats/ngs_receiving.parquet", "parquet"
        ),
    }
