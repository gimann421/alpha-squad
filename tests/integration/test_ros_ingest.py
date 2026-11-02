"""ROS data ingestion: local-file discovery, provenance manifest, schedule/ECR loaders."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from alpha_squad.config.settings import Settings
from alpha_squad.ros import ingest as ing
from alpha_squad.ros import snapshots as sn

pytestmark = pytest.mark.integration


def _touch(root, source, dataset, captured, name, content="x"):
    d = root / "raw" / source / dataset / f"captured_at={captured}"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(content)
    return d / name


def test_latest_local_picks_the_newest_capture_for_the_requested_season(tmp_path):
    s = Settings(data_dir=tmp_path)
    _touch(tmp_path, "nflverse", "stats_player_week", "2026-10-01", "season-2025_a.parquet")
    new = _touch(tmp_path, "nflverse", "stats_player_week", "2026-11-02", "season-2025_a.parquet")
    _touch(tmp_path, "nflverse", "stats_player_week", "2026-11-03", "season-2024_a.parquet")
    assert ing.latest_local(s, "nflverse", "stats_player_week", 2025) == new
    assert ing.latest_local(s, "nflverse", "stats_player_week", 2023) is None
    assert ing.latest_local(s, "dynastyprocess", "fp_ecr_history") is None


def test_manifest_records_hash_capture_date_and_size(tmp_path):
    p = _touch(tmp_path, "nfldata", "games", "2026-11-02", "default_games.csv", "abc")
    rec = ing._describe("nfldata", "games", None, p)
    assert rec.captured_at == "2026-11-02" and rec.bytes == 3 and len(rec.sha256) == 64
    out = tmp_path / "m.json"
    ing.write_manifest({"schedule": rec, "stats": {2025: rec}}, out)
    m = json.loads(out.read_text())
    assert m["schedule"]["sha256"] == rec.sha256 and m["stats"]["2025"]["dataset"] == "games"


def test_schedule_loader_builds_team_view_and_ignores_playoffs(tmp_path):
    p = tmp_path / "games.csv"
    pd.DataFrame(
        [
            dict(
                game_id="g1",
                season=2024,
                game_type="REG",
                week=1,
                gameday="2024-09-08",
                gametime="13:00",
                away_team="JAC",
                home_team="LAR",
                away_score=10,
                home_score=20,
            ),
            dict(
                game_id="g2",
                season=2024,
                game_type="POST",
                week=19,
                gameday="2025-01-12",
                gametime="13:00",
                away_team="JAC",
                home_team="LAR",
                away_score=1,
                home_score=2,
            ),
        ]
    ).to_csv(p, index=False)
    s = sn.load_schedule(p)
    assert len(s) == 2 and set(s.team) == {"JAX", "LA"}  # aliases normalised, playoffs dropped
    assert s[s.team == "LA"].iloc[0].pts_for == 20 and s[s.team == "JAX"].iloc[0].pts_against == 20


def test_ecr_loader_keeps_only_the_ros_qb_pages_and_both_historical_labels(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = []
    for page, d in (
        ("/nfl/rankings/ros-qb.php", "2024-10-11"),
        ("ros-qb", "2020-10-08"),
        ("/nfl/rankings/ros-ppr-wr.php", "2024-10-11"),
        ("/nfl/rankings/ros-qb.php", "2024-10-18"),
    ):
        rows.append(
            dict(
                fp_page=page,
                page_type="redraft-qb",
                player="P",
                id="1",
                pos="QB" if "wr" not in page else "WR",
                team="LAR",
                ecr=1.0,
                sd=0.0,
                best=1.0,
                worst=1.0,
                ecr_type="rp",
                scrape_date=d,
            )
        )
    rows.append(dict(rows[0], ecr=None))  # an unranked row must be ignored, never imputed
    f = tmp_path / "e.parquet"
    pq.write_table(pa.Table.from_pylist(rows), f)
    e = sn.load_ecr_qb(f)
    assert (
        sorted(map(str, e.scrape_date)) == ["2020-10-08", "2024-10-11", "2024-10-18"]
        and (e.team == "LA").all()
    )
    desc = sn.describe_ecr_archive(e)
    assert desc["has_point_projections"] is False and desc["n_scrapes"] == 3
