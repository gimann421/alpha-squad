"""``alpha-squad ros ...`` commands (D116). Registered in ``alpha_squad/cli.py``."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import typer
from rich.console import Console

ros_app = typer.Typer(help="Midseason ROS QB forecasting and trade decisions (D116)")
console = Console()


@ros_app.command("ingest")
def ros_ingest(
    start: int = typer.Option(
        2019,
        help="first season to fetch (prior-season features need start-1 of the first test season)",
    ),
    end: int = typer.Option(2026),
    refresh: bool = typer.Option(False, help="re-download even if a local copy exists"),
    out_dir: Path = typer.Option(Path("data/ros")),
) -> None:
    """Fetch/locate every raw input and write the provenance manifest."""
    from alpha_squad.ros.ingest import ensure_inputs, write_manifest

    files = ensure_inputs(list(range(start, end + 1)), refresh=refresh)
    write_manifest(files, out_dir / "inputs_manifest.json")
    for k, v in files.items():
        if isinstance(v, dict):
            console.print(
                f"{k}: {len(v)} seasons, newest capture {max(f.captured_at for f in v.values())}"
            )
        else:
            console.print(f"{k}: captured {v.captured_at} sha256 {v.sha256[:12]} {v.bytes:,} bytes")


@ros_app.command("build-panel")
def ros_build_panel(
    start: int = typer.Option(2020),
    end: int = typer.Option(2026),
    out_dir: Path = typer.Option(Path("data/ros")),
) -> None:
    """Build the leak-safe (season, snapshot, QB) panel and the all-position skill panel."""
    from alpha_squad.ros.pipeline import build_default_panel, build_skill_panel

    panel, inp = build_default_panel(list(range(start, end + 1)), out_dir=out_dir)
    specs = [s for s in inp.provenance["_specs"] if s.season < end or end <= 2025]
    sp, sw = build_skill_panel(
        inp, [s for s in specs if s.season <= 2025], inp.provenance["_files"], out_dir=out_dir
    )
    console.print(
        f"panel rows {len(panel)}  skill rows {len(sp)}  weekly rows {len(sw)}  -> {out_dir}"
    )
    console.print(f"ECR archive: {inp.provenance['ecr_archive']}")


@ros_app.command("backtest")
def ros_backtest(
    n_boot: int = typer.Option(4000, help="bootstrap draws"),
    out_dir: Path = typer.Option(Path("reports/ros")),
    rebuild_panel: bool = typer.Option(False, help="rebuild panels from raw files first"),
    skip_roster: bool = typer.Option(False),
    skip_mc: bool = typer.Option(False),
) -> None:
    """Re-run the entire walk-forward evaluation; writes CSVs and RESULTS.md under --out-dir."""
    from alpha_squad.ros.report import run_full_evaluation

    r = run_full_evaluation(
        out_dir=out_dir,
        n_boot=n_boot,
        rebuild_panel=rebuild_panel,
        skip_roster=skip_roster,
        skip_mc=skip_mc,
    )
    console.print(f"done -> {out_dir / 'RESULTS.md'}")
    console.print(
        json.dumps(
            {k: r["meta"][k] for k in ("git_sha", "n_snapshots", "train_sizes")}, default=str
        )
    )


@ros_app.command("find")
def ros_find(name: str = typer.Argument(..., help="player name fragment")) -> None:
    """Look up GSIS ids by name (names are for lookup only; the engine takes ids)."""
    from alpha_squad.ros.ingest import ensure_inputs

    f = ensure_inputs([2025])["player_ids"]
    ids = pd.read_csv(f.path, dtype=str, na_values=["NA"])
    hit = ids[ids["name"].str.contains(name, case=False, na=False) & ids["gsis_id"].notna()]
    console.print(
        hit[["name", "position", "team", "gsis_id", "fantasypros_id", "sleeper_id"]]
        .head(25)
        .to_string(index=False)
    )


def _fmt_board(b: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "ecr_rank",
        "player",
        "team",
        "ros_selected",
        "ros_p10",
        "ros_p90",
        "ros_A_ecr",
        "ros_S2D",
        "pred_avail",
        "ppg_app",
        "n_remaining",
        "fp_ros_proj",
    ]
    out = b[[c for c in cols if c in b.columns]].copy()
    return out.rename(
        columns={
            "ros_selected": "model_ROS",
            "ros_p10": "p10",
            "ros_p90": "p90",
            "ros_A_ecr": "ECR-implied",
            "ros_S2D": "S2D",
            "pred_avail": "avail",
        }
    )


@ros_app.command("board")
def ros_board(
    top: int = typer.Option(24),
    model: str = typer.Option(None, help="override the live model (default: ros.live.LIVE_MODEL)"),
    refresh: bool = typer.Option(
        True, help="re-fetch moving inputs (ECR archive, schedule, current-season stats)"
    ),
    fp: bool = typer.Option(True, help="query FantasyPros' live API for reference projections"),
    out_dir: Path = typer.Option(Path("reports/ros")),
) -> None:
    """Roster-independent QB board for the current week, with timestamps."""
    from alpha_squad.ros import live

    data = live.load_live(refresh=refresh)
    board, cal = live.forecast_qbs(data, model or live.LIVE_MODEL)
    fpd = (
        live.fp_live_projections(sorted({w for ws in data.fut_weeks.values() for w in ws}))
        if fp
        else {"available": False, "reason": "disabled"}
    )
    board = live.attach_fp(board, fpd, data.fut_weeks)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = data.today.isoformat()
    board.to_csv(out_dir / f"live_board_{stamp}.csv", index=False)
    meta = {
        "as_of": stamp,
        "snapshot": {
            "season": data.spec.season,
            "week": data.spec.week,
            "ecr_scrape": str(data.spec.scrape_date),
        },
        "model": cal["model"],
        "tau_points_per_game": cal["tau_play"],
        "inputs": {
            k: (
                v
                if not isinstance(v, dict) or "captured_at" in v
                else {s: f["captured_at"] for s, f in v.items()}
            )
            for k, v in data.inputs.items()
        },
        "fantasypros_live": {k: v for k, v in fpd.items() if k not in ("weekly",)},
    }
    (out_dir / f"live_board_{stamp}.json").write_text(json.dumps(meta, indent=2, default=str))
    console.print(
        f"[bold]QB board as of {stamp}[/bold] (ECR scrape {data.spec.scrape_date}, "
        f"age {int(board['ecr_age_days'].iloc[0])} d; model {cal['model']}; weeks {data.spec.week}+)"
    )
    console.print(
        _fmt_board(board.sort_values("ecr_rank").head(top)).round(1).to_string(index=False)
    )
    if not fpd.get("available"):
        console.print(
            f"[yellow]FantasyPros live projections unavailable: {fpd.get('reason')}[/yellow]"
        )


@ros_app.command("trade")
def ros_trade(
    config: Path = typer.Argument(
        ..., help="YAML: roster / targets / give / waiver_qbs / standings (see docs)"
    ),
    n_sims: int = typer.Option(4000),
    model: str = typer.Option(None),
    refresh: bool = typer.Option(True),
    fp: bool = typer.Option(True),
    out_dir: Path = typer.Option(Path("reports/ros")),
) -> None:
    """Evaluate concrete QB trades for a concrete roster, with simulation and sensitivity."""
    from alpha_squad.ros import live

    from alpha_squad.ros.scoring import ScoringRules

    league, ti = live.load_trade_yaml(config)
    rules = ScoringRules.from_league(league)
    panel_dir = Path("data/ros")
    if rules != ScoringRules.nflverse_ppr():
        # the league scores differently from the validated default (e.g. a different INT penalty):
        # rebuild the training panels under THIS league's scoring so forecasts are in its units
        import hashlib

        tag = hashlib.sha256(json.dumps(rules.describe(), sort_keys=True).encode()).hexdigest()[:8]
        panel_dir = Path(f"data/ros_{tag}")
        if not (panel_dir / "qb_ros_panel.parquet").exists():
            from alpha_squad.ros.pipeline import build_default_panel, build_skill_panel

            console.print(
                f"[yellow]league scoring differs from the default; building panels in {panel_dir}[/yellow]"
            )
            _, inp = build_default_panel(list(range(2020, 2027)), rules=rules, out_dir=panel_dir)
            build_skill_panel(
                inp,
                [x for x in inp.provenance["_specs"] if x.season <= 2025],
                inp.provenance["_files"],
                out_dir=panel_dir,
            )
        console.print(f"scoring: {rules.describe()}")
    data = live.load_live(refresh=refresh, panel_dir=panel_dir, rules=rules)
    board, cal = live.forecast_qbs(data, model or live.LIVE_MODEL)
    fpd = (
        live.fp_live_projections(sorted({w for ws in data.fut_weeks.values() for w in ws}))
        if fp
        else {"available": False}
    )
    board = live.attach_fp(board, fpd, data.fut_weeks)
    res, info = live.evaluate_candidates(league, data, board, cal, ti, n_sims=n_sims)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%MZ")
    res.to_json(out_dir / f"trade_eval_{stamp}.json", orient="records", indent=2)
    console.print(
        f"as of {data.today} | ECR scrape {data.spec.scrape_date} | unprojectable roster ids: {info['unprojectable_roster_ids']}"
    )
    show = [
        c
        for c in (
            "target",
            "give",
            "ecr_rank",
            "model_ros_points",
            "net_value_mean",
            "prob_improves",
            "net_p05",
            "net_p95",
            "max_cost_breakeven",
            "max_cost_conservative",
            "d_playoffs_pp",
            "d_champion_pp",
            "label",
        )
        if c in res.columns
    ]
    console.print(res[show].round(2).to_string(index=False))


@ros_app.command("forward-check")
def ros_forward_check(panel: Path = typer.Option(Path("data/ros/qb_ros_panel.parquet"))) -> None:
    """Truncated-horizon check of the frozen models on the season in progress."""
    from alpha_squad.ros.report import forward_check

    out = forward_check(pd.read_parquet(panel))
    console.print(
        out.groupby("model")[["pw_qb4_15", "pw_qb8_20", "spearman"]].mean().round(3).to_string()
    )


if __name__ == "__main__":  # pragma: no cover
    ros_app()
