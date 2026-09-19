"""W1 --- weekly-ranking foundation audit runner.

Reproduces every empirical number in `docs/weekly/W1_FOUNDATION_AUDIT.md`.

Two wirings, one audit implementation:

    --from-db      read the DynastyProcess snapshots this project already records
                   (`alpha-squad sources ingest`) plus its own `games` table. This is the
                   normal path and the one that preserves provenance.

    --from-files   read explicit local copies of the three source files. Used to produce W1's
                   numbers before a full ingest existed in this environment, and to re-check
                   the audit against a deliberately pinned vintage.

Neither wiring writes anything. This is a read-only measurement.

    uv run python scripts/research/w1_weekly_foundation_audit.py --from-db
    uv run python scripts/research/w1_weekly_foundation_audit.py --from-files \
        --ecr db_fpecr.parquet --xwalk db_playerids.csv --schedule nfl_games.csv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import duckdb

from alpha_squad.evaluation.weekly import audit
from alpha_squad.evaluation.weekly.scoring import FULL_PPR, HALF_PPR, STANDARD
from alpha_squad.evaluation.weekly.series import WEEKLY_OVERALL_SUPERFLEX, positional_series

DEFAULT_SEASONS = (2020, 2021, 2022, 2023, 2024, 2025)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _wire_from_files(con: duckdb.DuckDBPyConnection, args: argparse.Namespace) -> dict:
    """Register the audit's views over explicit local files, and pin their hashes.

    The hashes are the point: `db_fpecr.parquet` is a continuously-rebuilt mirror, so a number
    measured against it is only reproducible against a *named* vintage."""
    ecr, xwalk, schedule = Path(args.ecr), Path(args.xwalk), Path(args.schedule)
    for p in (ecr, xwalk, schedule):
        if not p.exists():
            sys.exit(f"missing input file: {p}")
    con.execute(f"CREATE VIEW ecr AS SELECT * FROM read_parquet('{ecr}')")
    con.execute(
        f"CREATE VIEW xwalk AS SELECT * FROM read_csv_auto('{xwalk}', "
        "types={'fantasypros_id':'VARCHAR','gsis_id':'VARCHAR'}, nullstr=['NA'])"
    )
    # The audit needs `games`; from files, build it from the nflverse schedule so the
    # schedule-dependent measurements use real kickoff dates rather than an assumed calendar.
    con.execute(
        f"""
        CREATE TABLE games AS
        SELECT game_id, season, week, game_type, CAST(gameday AS DATE) AS game_date,
               home_team, away_team
        FROM read_csv_auto('{schedule}') WHERE gameday IS NOT NULL
        """
    )
    return {
        "wiring": "files",
        "ecr_sha256": _sha256(ecr),
        "xwalk_sha256": _sha256(xwalk),
        "schedule_sha256": _sha256(schedule),
    }


def _wire_from_db(con: duckdb.DuckDBPyConnection, args: argparse.Namespace) -> dict:
    """Register the audit's views over this project's recorded snapshots.

    Uses `require_snapshot`, the same provenance-preserving reader `market/consensus.py` and
    `identity/canonical.py` use, so the audit reads the identical immutable file the market
    board was built from -- never a live re-fetch."""
    from alpha_squad.identity.canonical import reader_expr, require_snapshot

    db = Path(args.db)
    if not db.exists():
        sys.exit(f"no database at {db}; run `make ingest features market` first")
    con.execute(f"ATTACH '{db}' AS proj (READ_ONLY)")
    con.execute("USE proj")
    ecr_snap = require_snapshot(con, "dynastyprocess", "fp_ecr_history")
    xw_snap = require_snapshot(con, "dynastyprocess", "player_ids")
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW ecr AS SELECT * FROM {reader_expr(ecr_snap['local_path'])}"
    )
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW xwalk AS SELECT * FROM {reader_expr(xw_snap['local_path'])}"
    )
    return {
        "wiring": "db",
        "database": str(db),
        "ecr_snapshot_id": ecr_snap["snapshot_id"],
        "ecr_sha256": ecr_snap["sha256"],
        "ecr_captured_at": str(ecr_snap["captured_at"]),
        "xwalk_snapshot_id": xw_snap["snapshot_id"],
        "xwalk_sha256": xw_snap["sha256"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--from-db", action="store_true")
    mode.add_argument("--from-files", action="store_true")
    ap.add_argument("--db", default="data/alpha_squad.duckdb")
    ap.add_argument("--ecr", default="db_fpecr.parquet")
    ap.add_argument("--xwalk", default="db_playerids.csv")
    ap.add_argument("--schedule", default="nfl_games.csv")
    ap.add_argument("--seasons", default=",".join(str(s) for s in DEFAULT_SEASONS))
    ap.add_argument("--out", default="", help="write the full result as JSON to this path")
    args = ap.parse_args()

    seasons = tuple(int(s) for s in args.seasons.split(","))
    con = duckdb.connect()
    provenance = _wire_from_db(con, args) if args.from_db else _wire_from_files(con, args)

    result: dict = {"provenance": provenance, "seasons": list(seasons)}

    print("=" * 78)
    print("W1 WEEKLY FOUNDATION AUDIT")
    print("=" * 78)
    print(f"\nprovenance: {json.dumps(provenance, indent=2)}")

    print("\n--- 1. weekly ECR series present in the mirror ---")
    cov = audit.series_coverage(con)
    result["series_coverage"] = [c.__dict__ for c in cov]
    print(f"  {'series':<20}{'fp_page':<40}{'rows':>9}{'dates':>7}  span")
    for c in cov:
        print(
            f"  {c.series:<20}{c.fp_page:<40}{c.rows:>9}{c.scrape_dates:>7}"
            f"  {c.first_date} -> {c.last_date}"
        )

    print("\n--- 2. scrape-date weekday mix (the snapshot-cadence question) ---")
    mix = audit.scrape_date_weekday_mix(con)
    result["weekday_mix"] = mix
    for dow, n in mix.items():
        print(f"  {dow:<12}{n:>5}")

    print("\n--- 3. scoring formats available in the mirror (distinct fp_page matches) ---")
    fmt = audit.scoring_format_availability(con)
    result["scoring_format_pages"] = fmt
    for k, v in fmt.items():
        print(f"  {k:<12}{v:>5}")
    print(f"  -> Half-PPR ECR historically available: {'YES' if fmt['half'] else 'NO'}")

    print("\n--- 4. REG-week coverage (canonical snapshot per week) ---")
    wc = audit.week_coverage(con, seasons)
    result["covered_weeks"] = wc.covered
    result["uncovered_weeks"] = wc.uncovered
    by_season: dict[int, list[int]] = {}
    for s, w in wc.covered:
        by_season.setdefault(s, []).append(w)
    for s in seasons:
        weeks = sorted(by_season.get(s, []))
        print(f"  {s}: {len(weeks):>2} weeks  {weeks}")
    print(f"  TOTAL covered REG weeks: {wc.n_covered}")

    print("\n--- 5. already-played (Thursday-night) contamination on the benchmark board ---")
    contam = audit.already_played_contamination(con, wc.snapshots)
    result["contamination"] = contam
    for k, v in contam.items():
        print(f"  {k:<34}{v:>12.4g}")

    print("\n--- 6. identity join rate (board -> gsis_id) ---")
    joins = {}
    for series in (
        WEEKLY_OVERALL_SUPERFLEX,
        *(positional_series(p) for p in ("QB", "RB", "WR", "TE")),
    ):
        if series.team_coded:
            continue
        joins[str(series)] = audit.identity_join_rate(con, series)
        j = joins[str(series)]
        print(
            f"  {str(series):<20} rows={j['rows']:>8.0f}  matched={j['pct']:>6.2f}%"
            f"  top24={j['top24_pct']:>6.2f}%"
        )
    result["identity_join"] = joins

    print("\n--- 7. FLEX reconstruction: superflex board vs dedicated positional boards ---")
    flexc = {p: audit.flex_reconstruction_consistency(con, p) for p in ("RB", "WR", "TE", "QB")}
    result["flex_consistency"] = flexc
    print(f"  {'pos':<5}{'weeks':>7}{'median_n':>10}{'median_rho':>12}{'p10':>10}{'min':>10}")
    for p, d in flexc.items():
        if d.get("weeks"):
            print(
                f"  {p:<5}{d['weeks']:>7.0f}{d['median_n']:>10.0f}"
                f"{d['median_rho']:>12.4f}{d['p10_rho']:>10.4f}{d['min_rho']:>10.4f}"
            )

    print("\n--- 8. scoring-format identity (documentation of the derivation) ---")
    for f in (STANDARD, HALF_PPR, FULL_PPR):
        print(f"  {f.name:<12} pts/rec={f.points_per_reception:<5} SQL: {f.sql_expr('s')}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2, default=str))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
