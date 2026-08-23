"""DynastyProcess adapter. No auth required. Verified reachable 2026-08-20 via
raw.githubusercontent.com (the github.com/.../raw/... path is policy-blocked; the raw host is
not).

This is the operating substitute for the blocked FantasyPros API (`db_fpecr` for historical
ECR snapshots, `values-players` for current ECR/dynasty value including 2QB format) and for
the blocked KeepTradeCut site (`values-players`/`values-picks` dynasty value). See
docs/DECISIONS.md D3."""

from __future__ import annotations

from alpha_squad.sources.file_release import DatasetSpec, FileReleaseSourceAdapter

_BASE = "https://raw.githubusercontent.com/dynastyprocess/data/master/files"


class DynastyProcessSource(FileReleaseSourceAdapter):
    name = "dynastyprocess"
    datasets = {
        "player_ids": DatasetSpec("player_ids", f"{_BASE}/db_playerids.csv", "csv"),
        "fp_ecr_history": DatasetSpec("fp_ecr_history", f"{_BASE}/db_fpecr.parquet", "parquet"),
        "dynasty_values_players": DatasetSpec(
            "dynasty_values_players", f"{_BASE}/values-players.csv", "csv"
        ),
        "dynasty_values_picks": DatasetSpec(
            "dynasty_values_picks", f"{_BASE}/values-picks.csv", "csv"
        ),
    }
