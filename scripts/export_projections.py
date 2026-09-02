"""Export 2026 draft-pool projections to CSV, including the FantasyPros consensus board.

Mirrors the exact production player-pool assembly in league/replacement.py
(build_replacement_levels' point-source precedence): M6 uncertainty model for established
players, M7 rookie regression filling in true rookies the M6 model structurally excludes,
baseline_kdst filling in K/DST last. Adds the 1-QB redraft consensus board ('ro' /
'redraft-overall', the series Dilworth resolves to per D56) alongside it so market rank and
model projection are directly comparable in one file.

Usage:
    uv run python scripts/export_projections.py
    uv run python scripts/export_projections.py --season 2026 --out reports/projections_2026.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

from alpha_squad.config.settings import get_settings
from alpha_squad.models.baselines.kicking_defense import MODEL_NAME as KDST_MODEL_NAME
from alpha_squad.models.uncertainty.run import MODEL_VERSION as UNCERTAINTY_MODEL_VERSION
from alpha_squad.storage.db import get_connection

EXPORT_SQL = """
COPY (
    WITH consensus AS (
        SELECT player_id, ecr_rank, ecr_best, ecr_worst, scrape_date
        FROM (
            SELECT *,
                   row_number() OVER (
                       PARTITION BY player_id ORDER BY scrape_date DESC
                   ) AS rn
            FROM market_snapshot
            WHERE ecr_type = 'ro' AND page_type = 'redraft-overall'
        ) ranked
        WHERE rn = 1
    ),
    established AS (
        SELECT
            u.player_id, u.position, u.point_prediction AS projected_points,
            u.p10, u.p25, u.median AS median_points, u.p75, u.p90, u.confidence,
            'established_ml' AS source
        FROM uncertainty_predictions u
        WHERE u.season = ? AND u.model_version = ?
    ),
    rookies AS (
        SELECT
            r.player_id, r.position, r.predicted_rookie_points AS projected_points,
            NULL::DOUBLE AS p10, NULL::DOUBLE AS p25, NULL::DOUBLE AS median_points,
            NULL::DOUBLE AS p75, NULL::DOUBLE AS p90, r.breakout_probability AS confidence,
            'rookie_ml' AS source
        FROM rookie_predictions r
        WHERE r.draft_class = ?
          AND r.predicted_rookie_points IS NOT NULL
          AND r.player_id NOT IN (SELECT player_id FROM established)
    ),
    kdst AS (
        SELECT
            s.player_id, s.position, s.predicted_points AS projected_points,
            NULL::DOUBLE AS p10, NULL::DOUBLE AS p25, NULL::DOUBLE AS median_points,
            NULL::DOUBLE AS p75, NULL::DOUBLE AS p90, NULL::DOUBLE AS confidence,
            'baseline_kdst' AS source
        FROM projection_snapshot s
        WHERE s.model_name = ? AND s.season = ?
          AND s.player_id NOT IN (SELECT player_id FROM established)
    ),
    combined AS (
        SELECT * FROM established
        UNION ALL SELECT * FROM rookies
        UNION ALL SELECT * FROM kdst
    )
    SELECT
        p.display_name AS player,
        c.position,
        round(c.projected_points, 1) AS projected_points,
        round(c.p10, 1) AS floor_p10,
        round(c.median_points, 1) AS median,
        round(c.p90, 1) AS ceiling_p90,
        round(c.confidence, 2) AS confidence,
        c.source AS model_source,
        cm.ecr_rank AS consensus_rank,
        cm.ecr_best AS consensus_best_rank,
        cm.ecr_worst AS consensus_worst_rank,
        cm.scrape_date AS consensus_as_of
    FROM combined c
    JOIN players p ON p.player_id = c.player_id
    LEFT JOIN consensus cm ON cm.player_id = c.player_id
    ORDER BY c.projected_points DESC
) TO '{out_path}' (HEADER, DELIMITER ',')
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--out", type=str, default="reports/projections_2026.csv")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    con = get_connection(get_settings())
    con.execute(
        EXPORT_SQL.format(out_path=out_path.as_posix()),
        [args.season, UNCERTAINTY_MODEL_VERSION, args.season, KDST_MODEL_NAME, args.season],
    )
    con.close()

    n_rows = sum(1 for _ in out_path.open()) - 1
    print(f"wrote {n_rows} rows to {out_path}")


if __name__ == "__main__":
    main()
