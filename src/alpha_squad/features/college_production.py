"""College production via CFBD's `player_usage` dataset, identity-joined via `espn_id`
(docs/DECISIONS.md D38 — verified against real data: CFBD's numeric athlete IDs
(`player_usage.id`, `recruiting_players.athleteId`, `draft/picks.collegeAthleteId`) are the
same ID as DynastyProcess's `espn_id`, no fuzzy name matching involved). This supersedes D20's
"no verified ID bridge to cfbfastR-data" finding, which was about a different, unrelated ID
namespace (cfbfastR-data's play-by-play columns are ESPN-style numeric too, but that was never
checked against `espn_id` at the time — D20 only ruled out nflverse's slug-style `cfb_id`).

`build_college_usage` ingests one CFBD `player_usage` snapshot per requested season (a real,
timestamped, immutable capture per docs/DECISIONS.md D1's snapshot discipline — never a live
join at feature-build time) and upserts into `college_usage`, keyed by (player_id, season) so
re-running is idempotent. `features/rookie.py` then joins this in for each rookie's *final
college season only* (`rookie_season - 1`) — never the rookie's own NFL season — the same
leakage rule `landing_team_prior_pass_rate` already follows."""

from __future__ import annotations

import json

import duckdb
import pandas as pd

from alpha_squad.config.settings import Settings
from alpha_squad.sources.cfbd import CfbdSource
from alpha_squad.storage.snapshots import record_snapshot

# CFBD's `player/usage` endpoint returns an empty list for every season before 2013 — probed
# directly against the real API (1973, 1990, 2004, 2010 → `[]`; 2013 → 2991 rows). This is the
# real lower bound on college-usage coverage, and therefore on which draft classes can carry a
# college-production signal at all: a rookie's final college season is `rookie_season - 1`, so
# the earliest usable draft class is 2014.
CFBD_USAGE_FIRST_SEASON = 2013


def seasons_needed_for_rookies(con: duckdb.DuckDBPyConnection) -> list[int]:
    """The player's final college season is rookie_season - 1 — the season CFBD's
    `player_usage` needs to cover for every rookie already in the `players` spine, floored at
    CFBD_USAGE_FIRST_SEASON.

    The floor is not cosmetic: `players` spans the full nflverse history (rookie seasons back
    to the 1970s here), so an unfloored version issues ~40 real CFBD requests that every one
    return an empty list — verified empirically, not assumed (1973/1990/2004/2010 all returned
    `[]`, 2013 returned 2991 rows). That is wasted load on a third party's free API for zero
    rows. Shipped unfloored in D38 and corrected in D39."""
    rows = con.execute(
        """
        SELECT DISTINCT rookie_season - 1
        FROM players
        WHERE rookie_season IS NOT NULL AND position IN ('QB', 'RB', 'WR', 'TE')
          AND rookie_season - 1 >= ?
        ORDER BY 1
        """,
        [CFBD_USAGE_FIRST_SEASON],
    ).fetchall()
    return [r[0] for r in rows]


def build_college_usage(
    con: duckdb.DuckDBPyConnection, settings: Settings, seasons: list[int]
) -> int:
    cfbd = CfbdSource(settings)
    total = 0
    for season in seasons:
        snap = cfbd.fetch("player_usage", year=season)
        record_snapshot(con, snap)

        entries = json.loads(snap.local_path.read_bytes())
        if not entries:
            continue

        df = pd.DataFrame(
            {
                "cfbd_id": [str(e["id"]) for e in entries],
                "season": [e.get("season", season) for e in entries],
                "usage_overall": [e.get("usage", {}).get("overall") for e in entries],
                "usage_pass": [e.get("usage", {}).get("pass") for e in entries],
                "usage_rush": [e.get("usage", {}).get("rush") for e in entries],
            }
        )
        con.register("cfbd_usage_df", df)
        try:
            rows = con.execute(
                """
                INSERT INTO college_usage
                    (player_id, season, usage_overall, usage_pass, usage_rush, source_snapshot_id)
                SELECT
                    m.player_id, d.season, d.usage_overall, d.usage_pass, d.usage_rush, ?
                FROM cfbd_usage_df d
                JOIN player_id_map m ON m.id_type = 'espn_id' AND m.id_value = d.cfbd_id
                ON CONFLICT (player_id, season) DO UPDATE SET
                    usage_overall = excluded.usage_overall,
                    usage_pass = excluded.usage_pass,
                    usage_rush = excluded.usage_rush,
                    source_snapshot_id = excluded.source_snapshot_id
                RETURNING player_id
                """,
                [snap.snapshot_id],
            ).fetchall()
        finally:
            con.unregister("cfbd_usage_df")
        total += len(rows)
    return total
