"""W16 --- generate an EXPERIMENTAL prospective weekly board (W10 vs current Alpha).

**Beta product, not research.** Nothing here feeds the frozen 2026 holdout (W14 protocol): this
script imports W10's and production's functions read-only, opens every database read-only, fits
its models in memory, and writes only a snapshot file under `--out`.

  alpha_control     production's weekly CatBoost (`ml_catboost`), 11 features, QB/RB/WR/TE
  w10_experimental  W10's ALPHA_PLUS_HISTORICAL: the same model + 7 prior-season features, RB/WR/TE
                    (QB falls back to alpha_control, labelled; W10 has no QB model)
  K / DST           D57's season baseline / 17 for both selections (no weekly K/DST model exists)

Both models train exactly as their frozen definitions do: walk-forward, seasons [2015, S-1], once per
season, with production's loader order (the base database supplies the training frame, A2). What is
new is only the prediction frame: one row per eligible player built from the weekly roster and the
schedule, with features from production's own builders over games before the week
(`alpha_squad.beta.prospective`). No 2026 outcome is a training row, and no week-`w` game is an input.

    uv run python scripts/beta/weekly_board.py --season 2026 --week 5 \\
        --base-db data/alpha_squad.duckdb --db data/beta/alpha_squad_beta.duckdb \\
        --schedule <games.parquet> --out reports/beta
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alpha_squad.beta import prospective as pr  # noqa: E402
from alpha_squad.beta import weekly_board as wb  # noqa: E402
from alpha_squad.evaluation.weekly import arms as arms_mod  # noqa: E402
from alpha_squad.evaluation.weekly import mechanisms as mech  # noqa: E402
from alpha_squad.identity.canonical import reader_expr, require_snapshot  # noqa: E402
from alpha_squad.models.baselines.kicking_defense import (  # noqa: E402
    project_defenses,
    project_kickers,
)
from alpha_squad.models.established.data import load_position_week_data  # noqa: E402
from alpha_squad.models.established.features import FULL_FEATURES  # noqa: E402
from alpha_squad.models.established.train import (  # noqa: E402
    MODEL_SPECS,
    WEEKLY_PROJECTION_BASE_MODEL,
)
from scripts.research import w9_mechanisms as w9  # noqa: E402
from scripts.research import w10_historical as w10  # noqa: E402

MIN_TRAIN_SEASON = 2015
KDST_GAMES_PER_SEASON = 17
W10_FROZEN_COMMIT = "5de17c1"


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _snapshot_meta(con, source: str, dataset: str, generated_at: dt.datetime, **params) -> dict:
    """A state-type input (roster, injuries) must have been captured at or before the cutoff;
    otherwise the board would contain information from after it. Refuse rather than warn."""
    s = require_snapshot(con, source, dataset, **params)
    captured = s["captured_at"]
    captured = captured.replace(tzinfo=dt.UTC) if captured.tzinfo is None else captured
    if captured > generated_at:
        raise SystemExit(
            f"{source}/{dataset} was captured {captured.isoformat()}, after the board's cutoff "
            f"{generated_at.isoformat()}: a beta board can only be generated live, at its cutoff."
        )
    return {
        "source": source,
        "dataset": dataset,
        "params": params,
        "snapshot_id": s["snapshot_id"],
        "captured_at": captured.isoformat(),
        "sha256": s["sha256"],
        "local_path": s["local_path"],
    }


def _training_db(base, con, season: int, week: int) -> duckdb.DuckDBPyConnection:
    """In-memory database for the fits: the base database's training feature rows (seasons
    <= S-1) in its physical order, and every stats row strictly before week `week` for W9's
    durable table (whose season-S rows read season S-1 only)."""
    t = duckdb.connect()
    frames = {
        "player_week_features": base.execute(
            "SELECT * FROM player_week_features WHERE season <= ?", [season - 1]
        ).fetchdf(),
        "player_week_stats": con.execute(
            "SELECT * FROM player_week_stats WHERE season < ? OR (season = ? AND week < ?)",
            [season, season, week],
        ).fetchdf(),
    }
    for table, frame in frames.items():
        t.register("_f", frame)
        t.execute(f"CREATE TABLE {table} AS SELECT * FROM _f")
        t.unregister("_f")
    return t


def _complete_durable(dur: pd.DataFrame, season: int, player_ids: list[str]) -> pd.DataFrame:
    """W9's durable table has a (player, S) row only if the player played in S or S-1. In the
    holdout every evaluated player has played in S, so a player without an S-1 season always gets
    W10's "no prior season" values (`has_prior = 0`). A prospective player may not have played in
    S yet; give him exactly those values, from W10's own function, instead of an all-NaN row."""
    have = set(dur.loc[dur.season == season, "player_id"])
    add = [
        {"player_id": p, "season": season, **mech.durable_features([], None)}
        for p in sorted(set(player_ids) - have)
    ]
    return pd.concat([dur, pd.DataFrame(add)], ignore_index=True) if add else dur


def _append_prediction_rows(t, rows: pd.DataFrame, generated_at: dt.datetime) -> None:
    rows = rows.copy()
    rows["target_fantasy_points_ppr"] = None
    rows["feature_version"] = "beta_prospective"
    rows["built_at"] = generated_at.replace(tzinfo=None)
    cols = [
        c
        for c in rows.columns
        if c in {d[0] for d in t.execute("DESCRIBE player_week_features").fetchall()}
    ]
    t.register("_p", rows[cols])
    t.execute(
        f"INSERT INTO player_week_features ({', '.join(cols)}) SELECT {', '.join(cols)} FROM _p"
    )
    t.unregister("_p")


def main() -> None:  # noqa: PLR0915
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--base-db", default="data/alpha_squad.duckdb")
    ap.add_argument("--db", default="data/beta/alpha_squad_beta.duckdb")
    ap.add_argument("--schedule", required=True, help="nflverse schedules games.parquet snapshot")
    ap.add_argument("--generated-at", default=None, help="ISO UTC; default now")
    ap.add_argument(
        "--check-week", type=int, default=None, help="completed week for fidelity checks"
    )
    ap.add_argument("--out", default="reports/beta")
    args = ap.parse_args()

    season, week = args.season, args.week
    generated_at = (
        dt.datetime.fromisoformat(args.generated_at).astimezone(dt.UTC)
        if args.generated_at
        else dt.datetime.now(dt.UTC).replace(microsecond=0)
    )
    check_week = args.check_week if args.check_week is not None else week - 1

    con = duckdb.connect(args.db, read_only=True)
    base = duckdb.connect(args.base_db, read_only=True)

    print(f"[1/6] schedule, roster, identity (season {season} week {week}, cutoff {generated_at})")
    schedule_rows = (
        duckdb.sql(
            f"SELECT season, game_type, week, gameday, gametime, home_team, away_team, game_id "
            f"FROM {reader_expr(args.schedule)} WHERE season = {season}"
        )
        .df()
        .to_dict("records")
    )
    games = wb.week_games(schedule_rows, season, week)
    if not games:
        raise SystemExit(f"no REG games scheduled in {season} week {week}")

    roster_meta = _snapshot_meta(con, "nflverse", "weekly_rosters", generated_at, season=season)
    injury_meta = _snapshot_meta(con, "nflverse", "injuries", generated_at, season=season)
    roster_all = (
        con.execute(
            f"SELECT CAST(week AS INTEGER) AS week, team, position, status, gsis_id, full_name "
            f"FROM {reader_expr(roster_meta['local_path'])} WHERE season = ? AND game_type = 'REG'",
            [season],
        )
        .fetchdf()
        .to_dict("records")
    )
    roster_week_used, roster_rows = wb.roster_week_rows(roster_all, week)
    if roster_week_used is None:
        raise SystemExit(f"no weekly roster at or before week {week}")
    injuries = dict(
        con.execute(
            f"SELECT gsis_id, any_value(report_status) FROM {reader_expr(injury_meta['local_path'])} "
            "WHERE season = ? AND week = ? AND game_type = 'REG' AND report_status IS NOT NULL "
            "GROUP BY 1",
            [season, week],
        ).fetchall()
    )
    gsis_to_player = dict(
        con.execute("SELECT gsis_id, player_id FROM players WHERE gsis_id IS NOT NULL").fetchall()
    )
    season_teams = {r["home_team"] for r in schedule_rows if r["game_type"] == "REG"} | {
        r["away_team"] for r in schedule_rows if r["game_type"] == "REG"
    }
    entries, exclusions = wb.build_universe(
        roster_rows, games, gsis_to_player, generated_at, injuries, season_teams=season_teams
    )
    print(f"  {len(entries)} eligible, bye teams {exclusions.bye_teams}")

    print("[2/6] prospective feature rows (production builders, games before the week only)")
    team_slots = [
        pr.TeamSlot(t, g.kickoff_utc.astimezone(wb.ET).date()) for t, g in sorted(games.items())
    ]
    modelled = [e for e in entries if e.position in wb.MODEL_POSITIONS]
    slots = [
        pr.PlayerSlot(
            e.player_id, e.position, e.team, games[e.team].kickoff_utc.astimezone(wb.ET).date()
        )
        for e in modelled
    ]
    feats = pr.prospective_feature_rows(con, season, week, slots, team_slots)
    stats_max = con.execute(
        "SELECT max(week) FROM player_week_stats WHERE season = ? AND week < ?", [season, week]
    ).fetchone()[0]

    equivalence = pr.equivalence_check(con, season, check_week) if check_week >= 1 else None
    print(f"  equivalence on week {check_week}: {equivalence and equivalence['exact']}")

    # The check week's played players, rebuilt prospectively, ride along as extra prediction rows
    # (season S rows never enter a season-S fit) so the control can be compared with production.
    check_rows = pd.DataFrame()
    if check_week >= 1:
        played = con.execute(
            "SELECT s.player_id, s.position, s.team, s.game_date FROM player_week_stats s "
            "WHERE s.season = ? AND s.week = ? AND s.position IN ('QB','RB','WR','TE') "
            "ORDER BY 1",
            [season, check_week],
        ).fetchall()
        tg = con.execute(
            "SELECT team, game_date FROM team_week_stats WHERE season = ? AND week = ?",
            [season, check_week],
        ).fetchall()
        check_rows = pr.prospective_feature_rows(
            con,
            season,
            check_week,
            [pr.PlayerSlot(*r) for r in played],
            [pr.TeamSlot(*r) for r in tg],
        )

    print("[3/6] training frames (base database order) and fits")
    t = _training_db(base, con, season, week)
    frame_identical = {
        pos: bool(
            load_position_week_data(base, pos, MIN_TRAIN_SEASON, season - 1).equals(
                load_position_week_data(t, pos, MIN_TRAIN_SEASON, season - 1)
            )
        )
        for pos in wb.MODEL_POSITIONS
    }
    if not all(frame_identical.values()):
        raise SystemExit(f"training frame differs from the base database's: {frame_identical}")
    _append_prediction_rows(t, feats, generated_at)
    if not check_rows.empty:
        _append_prediction_rows(t, check_rows, generated_at)

    keys = ["player_id", "season", "week"]
    control = arms_mod.train_with_extra_features(
        t,
        pd.DataFrame(columns=keys),
        [],
        arm="ALPHA_CONTROL",
        seasons=(season,),
        positions=wb.MODEL_POSITIONS,
    )
    dur = _complete_durable(
        w9.durable_table(t, through=season),
        season,
        [e.player_id for e in modelled if e.position in wb.W10_POSITIONS],
    )
    panel_keys = t.execute(
        "SELECT player_id, season, week FROM player_week_features "
        "WHERE position IN ('RB','WR','TE')"
    ).fetchdf()
    extra = w9.durable_panel(panel_keys, dur, shuffle=False)
    w10_arm = arms_mod.train_with_extra_features(
        t,
        extra,
        list(mech.DURABLE_FEATURES),
        arm=w10.ARM_B,
        seasons=(season,),
        positions=wb.W10_POSITIONS,
    )

    print("[4/6] fidelity: control vs production's stored predictions on the check week")
    control_vs_prod = None
    if check_week >= 1:
        stored = dict(
            con.execute(
                "SELECT player_id, predicted_points FROM weekly_projection_snapshot "
                "WHERE model_name = ? AND season = ? AND week = ?",
                [WEEKLY_PROJECTION_BASE_MODEL, season, check_week],
            ).fetchall()
        )
        ours = control.for_week(season, check_week)
        common = sorted(set(stored) & set(ours))
        diffs = [abs(stored[p] - ours[p]) for p in common]
        control_vs_prod = {
            "week": check_week,
            "compared": len(common),
            "exact": sum(1 for d in diffs if d == 0.0),
            "max_abs_diff": max(diffs) if diffs else None,
            "note": (
                "production's stored predictions were not available on this database"
                if not stored
                else "exact equality requires the beta database to carry the base database's "
                "row order (W14 A2) when production's `train established` was run on it"
            ),
        }
        print(f"  {control_vs_prod}")

    # W10: the literal arm-B line of `w10_historical.trainings`, with W10's own panel, run on the
    # beta database's realized 2026 rows exactly as the W14 holdout runs it. The beta's prospective
    # W10 predictions for the check week's played players must equal it.
    w10_vs_frozen = None
    if check_week >= 1:
        from alpha_squad.evaluation.weekly import context
        from alpha_squad.evaluation.weekly import opportunity as op

        context.wire_snapshot_views(con, tuple(range(MIN_TRAIN_SEASON, season + 1)))
        panel = op.build_panel(con, w10.POSITIONS)
        dur_ref = w9.durable_table(con, through=season)
        ref = arms_mod.train_with_extra_features(
            con,
            w9.durable_panel(panel, dur_ref, shuffle=False),
            list(mech.DURABLE_FEATURES),
            arm=w10.ARM_B,
            seasons=(season,),
        )
        ref_w = ref.for_week(season, check_week)
        ours_w = w10_arm.for_week(season, check_week)
        common = sorted(set(ref_w) & set(ours_w))
        diffs = [abs(ref_w[p] - ours_w[p]) for p in common]
        w10_vs_frozen = {
            "week": check_week,
            "reference_players": len(ref_w),
            "compared": len(common),
            "exact": sum(1 for d in diffs if d == 0.0),
            "max_abs_diff": max(diffs) if diffs else None,
        }
        print(f"  w10 vs frozen path: {w10_vs_frozen}")

    print("[5/6] projections, K/DST baseline, inputs")
    projections = {m: {} for m in wb.MODELS}
    sources = {m: {} for m in wb.MODELS}
    a_week = control.for_week(season, week)
    b_week = w10_arm.for_week(season, week)
    for e in modelled:
        projections[wb.CONTROL][e.player_id] = a_week.get(e.player_id)
        sources[wb.CONTROL][e.player_id] = f"alpha_control:{WEEKLY_PROJECTION_BASE_MODEL}"
        if e.position in wb.W10_POSITIONS:
            projections[wb.W10][e.player_id] = b_week.get(e.player_id)
            sources[wb.W10][e.player_id] = f"w10:{w10.ARM_B}"
        else:
            projections[wb.W10][e.player_id] = a_week.get(e.player_id)
            sources[wb.W10][e.player_id] = "alpha_control (W10 has no QB model)"
    kdst = {**project_kickers(con, season), **project_defenses(con, season)}
    for e in entries:
        if e.position in wb.KDST_POSITIONS:
            v = kdst.get(e.player_id)
            for m in wb.MODELS:
                projections[m][e.player_id] = None if v is None else v / KDST_GAMES_PER_SEASON
                sources[m][e.player_id] = (
                    "kdst_season_baseline/17 (D57; no weekly model)"
                    if v is not None
                    else "no projection: no prior-season K/DST history"
                )
    missing = [e.player_id for e in modelled if projections[wb.CONTROL].get(e.player_id) is None]
    if missing:
        raise SystemExit(f"{len(missing)} modelled players got no prediction: {missing[:5]}")

    dur_s = dur[dur.season == season].set_index("player_id")
    inputs: dict[str, dict] = {}
    for r in feats.to_dict("records"):
        d = {c: (None if pd.isna(r[c]) else float(r[c])) for c in FULL_FEATURES}
        if r["player_id"] in dur_s.index:
            row = dur_s.loc[r["player_id"]]
            d |= {c: (None if pd.isna(row[c]) else float(row[c])) for c in mech.DURABLE_FEATURES}
        inputs[r["player_id"]] = d

    data_sources = [roster_meta, injury_meta]
    for ds in ("stats_player_week", "stats_team_week"):
        data_sources.append(_snapshot_meta(con, "nflverse", ds, generated_at, season=season))
    data_sources.append(
        {
            "source": "nflverse",
            "dataset": "schedules",
            "local_path": args.schedule,
            "sha256": _sha256(args.schedule),
        }
    )
    models = {
        wb.CONTROL: {
            "label": "Current Alpha (control)",
            "status": "production weekly model",
            "model": WEEKLY_PROJECTION_BASE_MODEL,
            "hyperparameters": {k: v for k, v in MODEL_SPECS["ml_catboost"][1].items()},
            "features": list(FULL_FEATURES),
            "positions": list(wb.MODEL_POSITIONS),
            "training_seasons": [MIN_TRAIN_SEASON, season - 1],
            "target": "Full-PPR points",
        },
        wb.W10: {
            "label": "W10 historical-player knowledge (EXPERIMENTAL)",
            "status": "experimental: 2026 holdout INCONCLUSIVE at 4 of 8 required weeks (W15/D123)",
            "model": w10.ARM_B,
            "frozen_code_commit": W10_FROZEN_COMMIT,
            "features": list(FULL_FEATURES) + list(mech.DURABLE_FEATURES),
            "positions": list(wb.W10_POSITIONS),
            "qb": "falls back to alpha_control",
            "training_seasons": [MIN_TRAIN_SEASON, season - 1],
            "target": "Full-PPR points",
        },
    }
    checks = {
        "stats_weeks_used_max": stats_max,
        "stats_rule": f"features use only games with week < {week} (row-level filter)",
        "prospective_rows": len(feats),
        "eligible_modelled_players": len(modelled),
        "training_frame_identical_to_base": frame_identical,
        "feature_equivalence": equivalence,
        "control_vs_production": control_vs_prod,
        "w10_vs_frozen_path": w10_vs_frozen,
        "w10_predictions": len(b_week),
    }

    print("[6/6] writing snapshot")
    snap = wb.assemble_snapshot(
        season=season,
        week=week,
        generated_at=generated_at,
        entries=entries,
        exclusions=exclusions,
        projections=projections,
        sources=sources,
        inputs=inputs,
        models=models,
        data_sources=data_sources,
        roster_week_used=roster_week_used,
        checks=checks,
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"weekly_board_{season}_w{week:02d}_{snap['snapshot_id'][:12]}"
    (out / f"{stem}.json").write_text(json.dumps(snap, indent=1, sort_keys=True, default=str))
    with (out / f"{stem}.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "model",
                "scoring",
                "view",
                "rank",
                "player_id",
                "name",
                "position",
                "team",
                "opponent",
                "projected_points",
                "game_started",
                "roster_status",
                "injury_status",
            ]
        )
        by_id = {p["player_id"]: p for p in snap["players"]}
        for m in wb.MODELS:
            for s in wb.SCORINGS:
                for v in wb.VIEWS:
                    for n, pid in enumerate(snap["boards"][m][s][v], start=1):
                        p = by_id[pid]
                        w.writerow(
                            [
                                m,
                                s,
                                v,
                                n,
                                pid,
                                p["name"],
                                p["position"],
                                p["team"],
                                p["opponent"],
                                p["projections"][m][s],
                                p["game_started"],
                                p["roster_status"],
                                p["injury_status"],
                            ]
                        )
    print(f"wrote {out / stem}.json (+ .csv); snapshot {snap['snapshot_id']}")


if __name__ == "__main__":
    main()
