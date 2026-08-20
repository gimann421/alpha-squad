"""Real, structured evidence events derived from officially-sourced nflverse data
(D5/D22: Medium/Weak sources -- beat writers, coach comments, social media -- require a
news/social API this environment cannot reach; only PRODUCT_SPEC.md's Strong-tier signals,
all official/structured, have a detector here: depth-chart moves, injury reports, roster
transactions, usage-share shifts).

Every detector produces evidence dated so it is available strictly before the week it
informs starts (leakage-safe by construction, same discipline as features/panel.py): depth
chart and roster comparisons use the *entering* state as of the week's first game date, and
injury/usage detectors read the just-completed week's real report/production, never the
target week's own outcome."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import duckdb

from alpha_squad.evidence.taxonomy import strength_for
from alpha_squad.identity.canonical import reader_expr, require_snapshot
from alpha_squad.sources.base import utcnow

USAGE_SHARE_SHIFT_THRESHOLD = 0.15  # 15 percentage points, target_share or snap_pct


@dataclass
class EvidenceBuildReport:
    events_written: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    def bump(self, event_type: str, n: int) -> None:
        if n:
            self.by_type[event_type] = self.by_type.get(event_type, 0) + n
            self.events_written += n


def _event_id(player_id: str, season: int, week: int, event_type: str, detail_key: str) -> str:
    digest = hashlib.md5(
        f"{player_id}:{season}:{week}:{event_type}:{detail_key}".encode()
    ).hexdigest()[:16]
    return f"ev_{digest}"


def _week_start_dates(con: duckdb.DuckDBPyConnection, season: int) -> dict[int, str]:
    rows = con.execute(
        "SELECT week, min(game_date) FROM games WHERE season = ? GROUP BY 1", [season]
    ).fetchall()
    return {week: str(d) for week, d in rows}


def record_event(
    con: duckdb.DuckDBPyConnection,
    *,
    player_id: str,
    season: int,
    week: int,
    event_date: str,
    event_type: str,
    source: str,
    direction: int,
    structured_impact: dict,
    summary: str,
    source_url: str | None = None,
    source_snapshot_id: str | None = None,
) -> str:
    label, score = strength_for(event_type)
    detail_json = json.dumps(structured_impact, sort_keys=True)
    event_id = _event_id(player_id, season, week, event_type, detail_json)
    con.execute(
        """
        INSERT INTO evidence_events
            (event_id, player_id, season, week, event_date, captured_at, event_type, source,
             source_url, strength_label, strength, direction, structured_impact_json, summary,
             source_snapshot_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (event_id) DO NOTHING
        """,
        [
            event_id,
            player_id,
            season,
            week,
            event_date,
            utcnow(),
            event_type,
            source,
            source_url,
            label,
            score,
            direction,
            detail_json,
            summary,
            source_snapshot_id,
        ],
    )
    return event_id


_SKILL_ABB = ("QB", "RB", "WR", "TE")


def _depth_chart_entering(
    con: duckdb.DuckDBPyConnection,
    season: int,
    week: int,
    week_starts: dict[int, str],
    table_name: str,
) -> str | None:
    """Materializes a temp table `table_name` with columns (gsis_id, team, pos_abb,
    pos_rank) for the depth chart as known *entering* `week` (never later), restricted to
    QB/RB/WR/TE. Handles nflverse's two real historical depth_charts schemas (D24): the
    2025+ near-daily `dt`-keyed format (take the latest snapshot strictly before the week's
    first game) and the pre-2025 explicit `week`-keyed format (there is no sub-week
    timestamp, so "entering week W" is the filing for week W-1, the most recent fully-known
    week strictly before W -- conservative but leakage-safe either way). Returns the source
    snapshot_id, or None if `week` has no games table entry at all.
    """
    if week not in week_starts:
        return None
    snap = require_snapshot(con, "nflverse", "depth_charts", season=season)
    src = reader_expr(snap["local_path"])
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()}

    if "dt" in cols:
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE {table_name} AS
            SELECT gsis_id, team, pos_abb, pos_rank FROM (
                SELECT gsis_id, team, pos_abb, pos_rank,
                       row_number() OVER (PARTITION BY gsis_id, team, pos_abb ORDER BY dt DESC) AS rn
                FROM {src}
                WHERE CAST(dt AS TIMESTAMP) < CAST(? AS DATE) AND pos_abb IN ('QB', 'RB', 'WR', 'TE')
            ) WHERE rn = 1
            """,
            [week_starts[week]],
        )
    else:
        if week - 1 < 1:
            con.execute(
                f"CREATE OR REPLACE TEMP TABLE {table_name} AS SELECT NULL::VARCHAR AS gsis_id, NULL::VARCHAR AS team, NULL::VARCHAR AS pos_abb, NULL::INTEGER AS pos_rank WHERE FALSE"
            )
            return snap["snapshot_id"]
        con.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE {table_name} AS
            SELECT gsis_id, club_code AS team, depth_position AS pos_abb,
                   TRY_CAST(depth_team AS INTEGER) AS pos_rank
            FROM {src}
            WHERE week = ? AND formation = 'Offense' AND depth_position IN ('QB', 'RB', 'WR', 'TE')
            """,
            [week - 1],
        )
    return snap["snapshot_id"]


def detect_depth_chart_moves(
    con: duckdb.DuckDBPyConnection, season: int, week: int, week_starts: dict[int, str]
) -> int:
    if week not in week_starts or (week - 1) not in week_starts:
        return 0
    snapshot_id = _depth_chart_entering(con, season, week, week_starts, "_dc_this")
    _depth_chart_entering(con, season, week - 1, week_starts, "_dc_prev")
    if snapshot_id is None:
        return 0

    rows = con.execute(
        """
        SELECT p.player_id, t.team, t.pos_abb, pr.pos_rank AS prior_rank, t.pos_rank AS new_rank
        FROM _dc_this t
        JOIN _dc_prev pr ON pr.gsis_id = t.gsis_id AND pr.team = t.team AND pr.pos_abb = t.pos_abb
        JOIN players p ON p.gsis_id = t.gsis_id
        WHERE pr.pos_rank != t.pos_rank
        """
    ).fetchall()

    for player_id, team, pos_abb, prior_rank, new_rank in rows:
        promoted = new_rank < prior_rank
        event_type = "depth_chart_promotion" if promoted else "depth_chart_demotion"
        record_event(
            con,
            player_id=player_id,
            season=season,
            week=week,
            event_date=week_starts[week - 1],
            event_type=event_type,
            source="nflverse_depth_charts",
            direction=1 if promoted else -1,
            structured_impact={
                "team": team,
                "position": pos_abb,
                "prior_rank": prior_rank,
                "new_rank": new_rank,
            },
            summary=f"{pos_abb} depth chart rank {prior_rank} -> {new_rank} at {team}",
            source_snapshot_id=snapshot_id,
        )
    return len(rows)


def detect_injury_events(
    con: duckdb.DuckDBPyConnection, season: int, week: int, week_starts: dict[int, str]
) -> int:
    if week not in week_starts:
        return 0
    inj_snap = require_snapshot(con, "nflverse", "injuries", season=season)
    inj_src = reader_expr(inj_snap["local_path"])

    self_rows = con.execute(
        f"""
        SELECT p.player_id, i.report_status
        FROM {inj_src} i
        JOIN players p ON p.gsis_id = i.gsis_id
        WHERE i.week = ? AND i.report_status IN ('Out', 'Doubtful')
        """,
        [week],
    ).fetchall()
    n = 0
    for player_id, status in self_rows:
        record_event(
            con,
            player_id=player_id,
            season=season,
            week=week,
            event_date=week_starts[week],
            event_type="injury_own_status",
            source="nflverse_injuries",
            direction=-1,
            structured_impact={"report_status": status},
            summary=f"Listed {status} on the week {week} injury report",
            source_snapshot_id=inj_snap["snapshot_id"],
        )
        n += 1

    dc_snapshot_id = _depth_chart_entering(con, season, week, week_starts, "_dc_for_injury")
    if dc_snapshot_id is None:
        return n
    beneficiary_rows = con.execute(
        f"""
        WITH out_players AS (
            SELECT i.gsis_id, dc.team, dc.pos_abb, dc.pos_rank
            FROM {inj_src} i
            JOIN _dc_for_injury dc ON dc.gsis_id = i.gsis_id
            WHERE i.week = ? AND i.report_status IN ('Out', 'Doubtful')
        )
        SELECT p.player_id, o.team, o.pos_abb, o.pos_rank AS injured_rank, dc.pos_rank AS beneficiary_rank
        FROM out_players o
        JOIN _dc_for_injury dc ON dc.team = o.team AND dc.pos_abb = o.pos_abb AND dc.pos_rank = o.pos_rank + 1
        JOIN players p ON p.gsis_id = dc.gsis_id
        """,
        [week],
    ).fetchall()
    for player_id, team, pos_abb, injured_rank, beneficiary_rank in beneficiary_rows:
        record_event(
            con,
            player_id=player_id,
            season=season,
            week=week,
            event_date=week_starts[week],
            event_type="injury_teammate_opportunity",
            source="nflverse_injuries+depth_charts",
            direction=1,
            structured_impact={
                "team": team,
                "position": pos_abb,
                "injured_rank": injured_rank,
                "beneficiary_rank": beneficiary_rank,
            },
            summary=f"{pos_abb}{injured_rank} at {team} ruled out/doubtful; next man up",
            source_snapshot_id=dc_snapshot_id,
        )
    return n + len(beneficiary_rows)


def detect_roster_transactions(
    con: duckdb.DuckDBPyConnection, season: int, week: int, week_starts: dict[int, str]
) -> int:
    if week not in week_starts or week < 3:
        return 0
    snap = require_snapshot(con, "nflverse", "weekly_rosters", season=season)
    src = reader_expr(snap["local_path"])

    rows = con.execute(
        f"""
        SELECT p.player_id, r1.team AS new_team, r2.team AS prior_team
        FROM {src} r1
        JOIN {src} r2 ON r2.gsis_id = r1.gsis_id AND r2.week = ?
        JOIN players p ON p.gsis_id = r1.gsis_id
        WHERE r1.week = ? AND r1.team != r2.team
        """,
        [week - 2, week - 1],
    ).fetchall()
    for player_id, new_team, prior_team in rows:
        record_event(
            con,
            player_id=player_id,
            season=season,
            week=week,
            event_date=week_starts[week - 1],
            event_type="roster_transaction",
            source="nflverse_weekly_rosters",
            direction=0,
            structured_impact={"prior_team": prior_team, "new_team": new_team},
            summary=f"Roster change: {prior_team} -> {new_team}",
            source_snapshot_id=snap["snapshot_id"],
        )
    return len(rows)


def detect_usage_share_shifts(
    con: duckdb.DuckDBPyConnection, season: int, week: int, week_starts: dict[int, str]
) -> int:
    if week not in week_starts or (week - 1) not in week_starts:
        return 0
    rows = con.execute(
        """
        SELECT pws.player_id, pws.target_share, pwf.target_share_avg_last3,
               pws.offense_snap_pct, pwf.snap_pct_avg_last3
        FROM player_week_stats pws
        JOIN player_week_features pwf
          ON pwf.player_id = pws.player_id AND pwf.season = pws.season AND pwf.week = pws.week
        WHERE pws.season = ? AND pws.week = ?
        """,
        [season, week - 1],
    ).fetchall()

    n = 0
    for player_id, target_share, target_share_avg, snap_pct, snap_pct_avg in rows:
        for actual, trailing_avg, metric in (
            (target_share, target_share_avg, "target_share"),
            (snap_pct, snap_pct_avg, "snap_pct"),
        ):
            if actual is None or trailing_avg is None:
                continue
            delta = actual - trailing_avg
            if abs(delta) < USAGE_SHARE_SHIFT_THRESHOLD:
                continue
            event_type = "usage_share_spike" if delta > 0 else "usage_share_drop"
            record_event(
                con,
                player_id=player_id,
                season=season,
                week=week,
                event_date=week_starts[week - 1],
                event_type=event_type,
                source="nflverse_stats_player_week",
                direction=1 if delta > 0 else -1,
                structured_impact={
                    "metric": metric,
                    "week_value": actual,
                    "trailing_avg_last3": trailing_avg,
                    "delta": delta,
                },
                summary=f"{metric} {actual:.2f} vs trailing avg {trailing_avg:.2f} in week {week - 1}",
            )
            n += 1
    return n


def build_evidence_events(
    con: duckdb.DuckDBPyConnection, season: int, week: int
) -> EvidenceBuildReport:
    report = EvidenceBuildReport()
    week_starts = _week_start_dates(con, season)
    if week not in week_starts:
        report.skipped.append(f"{season}/week{week}: no games table entry")
        return report

    report.bump(
        "depth_chart_promotion/demotion", detect_depth_chart_moves(con, season, week, week_starts)
    )
    report.bump("injury_events", detect_injury_events(con, season, week, week_starts))
    report.bump("roster_transaction", detect_roster_transactions(con, season, week, week_starts))
    report.bump("usage_share_shift", detect_usage_share_shifts(con, season, week, week_starts))
    return report


def build_evidence_events_range(
    con: duckdb.DuckDBPyConnection, season_start: int, season_end: int
) -> EvidenceBuildReport:
    total = EvidenceBuildReport()
    for season in range(season_start, season_end + 1):
        max_week = con.execute("SELECT max(week) FROM games WHERE season = ?", [season]).fetchone()[
            0
        ]
        if max_week is None:
            total.skipped.append(f"{season}: no games ingested")
            continue
        for week in range(2, max_week + 1):
            sub = build_evidence_events(con, season, week)
            for event_type, n in sub.by_type.items():
                total.bump(event_type, n)
            total.skipped.extend(sub.skipped)
    return total
