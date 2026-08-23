"""cfbfastR-data adapter. No auth required. Verified reachable 2026-08-20 via
raw.githubusercontent.com. Operating substitute for the blocked CollegeFootballData API
(college production for rookie modeling) — see docs/DECISIONS.md D3."""

from __future__ import annotations

from alpha_squad.sources.file_release import DatasetSpec, FileReleaseSourceAdapter

_BASE = "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main"


class CfbFastRSource(FileReleaseSourceAdapter):
    name = "cfbfastr"
    datasets = {
        "player_stats": DatasetSpec(
            "player_stats",
            f"{_BASE}/player_stats/parquet/player_stats_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2025,
        ),
    }
