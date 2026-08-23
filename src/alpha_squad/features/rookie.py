"""Builds `rookie_features`: one row per skill-position player's actual rookie NFL season,
combining draft capital (from the `players` spine, gsis_id-linked), combine athletic testing
(`combine_results`, pfr_id-linked), and landing spot (the drafting team's *prior* season pass
rate/play volume — using only information genuinely known before the rookie's own season, to
avoid a look-ahead: a team's full-season stats for the rookie's own season aren't known at
draft time, but the team the rookie landed on and that team's most recent prior season are).

College production is deliberately absent — no verified ID bridge to cfbfastR-data exists
(docs/DECISIONS.md D20).

Set-based INSERT...SELECT, not a Python row loop — a Python-loop version of this exact
pattern was found to take 88s/25k rows in M2's identity build (docs/DECISIONS.md, the M2
insert_id_mappings fix); this table is smaller (~1k rows) but there's no reason to
reintroduce the same anti-pattern."""

from __future__ import annotations

import duckdb

from alpha_squad.sources.base import utcnow


def build_rookie_features(con: duckdb.DuckDBPyConnection) -> int:
    rows = con.execute(
        """
        INSERT INTO rookie_features (
            player_id, draft_class, position, draft_round, draft_pick, forty, bench,
            vertical, broad_jump, cone, shuttle, height, weight,
            landing_team_prior_pass_rate, landing_team_prior_plays,
            rookie_year_ppr_points, rookie_year_games, breakout_top24, built_at
        )
        WITH team_season AS (
            SELECT team, season, AVG(pass_rate) AS avg_pass_rate, AVG(plays) AS avg_plays
            FROM team_week_stats
            GROUP BY team, season
        ),
        position_rank AS (
            SELECT
                player_id, season,
                row_number() OVER (PARTITION BY season, position ORDER BY total_fantasy_points_ppr DESC) AS pos_rank
            FROM player_season_stats
            WHERE position IN ('QB', 'RB', 'WR', 'TE')
        )
        SELECT
            p.player_id, p.rookie_season, p.position,
            p.draft_round, p.draft_pick,
            cr.forty, cr.bench, cr.vertical, cr.broad_jump, cr.cone, cr.shuttle, cr.height, cr.weight,
            ts.avg_pass_rate, ts.avg_plays,
            rs.total_fantasy_points_ppr, rs.games_played,
            (pr.pos_rank <= 24), ?
        FROM players p
        JOIN player_season_stats rs ON rs.player_id = p.player_id AND rs.season = p.rookie_season
        LEFT JOIN combine_results cr ON cr.player_id = p.player_id
        LEFT JOIN team_season ts ON ts.team = p.draft_team AND ts.season = p.rookie_season - 1
        LEFT JOIN position_rank pr ON pr.player_id = rs.player_id AND pr.season = rs.season
        WHERE p.rookie_season IS NOT NULL AND p.position IN ('QB', 'RB', 'WR', 'TE')
        ON CONFLICT (player_id) DO UPDATE SET
            draft_class = excluded.draft_class, position = excluded.position,
            draft_round = excluded.draft_round, draft_pick = excluded.draft_pick,
            forty = excluded.forty, bench = excluded.bench, vertical = excluded.vertical,
            broad_jump = excluded.broad_jump, cone = excluded.cone, shuttle = excluded.shuttle,
            height = excluded.height, weight = excluded.weight,
            landing_team_prior_pass_rate = excluded.landing_team_prior_pass_rate,
            landing_team_prior_plays = excluded.landing_team_prior_plays,
            rookie_year_ppr_points = excluded.rookie_year_ppr_points,
            rookie_year_games = excluded.rookie_year_games,
            breakout_top24 = excluded.breakout_top24, built_at = excluded.built_at
        RETURNING player_id
        """,
        [utcnow()],
    ).fetchall()
    return len(rows)
