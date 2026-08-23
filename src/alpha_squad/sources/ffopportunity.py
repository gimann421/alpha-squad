"""ffverse ffopportunity adapter. No auth required. Verified reachable 2026-08-20. Provides
expected-fantasy-points-per-play data used by the opportunity model (ARCHITECTURE.md §5)."""

from __future__ import annotations

from alpha_squad.sources.file_release import DatasetSpec, FileReleaseSourceAdapter

_BASE = "https://github.com/ffverse/ffopportunity/releases/download/latest-data"


class FfOpportunitySource(FileReleaseSourceAdapter):
    name = "ffopportunity"
    datasets = {
        "ep_weekly": DatasetSpec(
            "ep_weekly",
            f"{_BASE}/ep_weekly_{{season}}.parquet",
            "parquet",
            requires_season=True,
            default_health_season=2025,
        ),
    }
