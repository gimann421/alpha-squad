"""Alpha Squad CLI entry point. `uv run alpha-squad --help` for the full command tree."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from alpha_squad.config.settings import get_settings
from alpha_squad.features.build import build_features
from alpha_squad.identity.canonical import build_identity
from alpha_squad.identity.exceptions import list_exceptions
from alpha_squad.market.consensus import build_market_snapshot
from alpha_squad.models.baselines.run import run_baselines
from alpha_squad.models.established.season_level import run_season_level_established_ml
from alpha_squad.models.established.train import run_established_ml
from alpha_squad.models.report import write_evaluation_report
from alpha_squad.models.uncertainty.run import run_uncertainty
from alpha_squad.sources.base import SourceError, SourceHealth, SourceStatus, utcnow
from alpha_squad.sources.registry import all_adapters
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_health, record_snapshot

app = typer.Typer(help="Alpha Squad — fantasy football market-inefficiency intelligence system")
sources_app = typer.Typer(help="Data source operations")
identity_app = typer.Typer(help="Canonical player identity operations")
features_app = typer.Typer(help="As-of feature store operations")
market_app = typer.Typer(help="Market consensus operations")
evaluate_app = typer.Typer(help="Baseline/model evaluation operations")
train_app = typer.Typer(help="Model training operations")
app.add_typer(sources_app, name="sources")
app.add_typer(identity_app, name="identity")
app.add_typer(features_app, name="features")
app.add_typer(market_app, name="market")
app.add_typer(evaluate_app, name="evaluate")
app.add_typer(train_app, name="train")
console = Console()

# Datasets that vary by NFL season vs. ones that are a single current/whole-history file.
_SEASONAL: dict[str, list[str]] = {
    "nflverse": [
        "stats_player_week",
        "stats_team_week",
        "rosters",
        "weekly_rosters",
        "depth_charts",
        "injuries",
        "snap_counts",
        "pbp",
        "ftn_charting",
    ],
    "cfbfastr": ["player_stats"],
    "ffopportunity": ["ep_weekly"],
}
_NON_SEASONAL: dict[str, list[str]] = {
    "nflverse": [
        "players",
        "draft_picks",
        "combine",
        "ngs_passing",
        "ngs_rushing",
        "ngs_receiving",
    ],
    "dynastyprocess": [
        "player_ids",
        "fp_ecr_history",
        "dynasty_values_players",
        "dynasty_values_picks",
    ],
}


@sources_app.command("status")
def sources_status() -> None:
    """Check every registered data source and report AVAILABLE / BLOCKED_BY_POLICY /
    NO_CREDENTIALS / ERROR per dataset. Always performs a real check — never assumes a
    source works because the docs say it should. Every successful check writes a real
    snapshot to disk and registers it, same as `sources ingest` — a status check and an
    ingest of the default health params are the same operation here, not two code paths
    that could silently disagree."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    table = Table(title="Data source status")
    for col in ("source", "dataset", "status", "detail"):
        table.add_column(col)

    exit_code = 0
    for adapter in all_adapters(settings):
        for dataset in adapter.list_datasets():
            checked_at = utcnow()
            try:
                snap = adapter.fetch(dataset, **adapter.default_health_params(dataset))
                record_snapshot(con, snap)
                status_value, detail = (
                    "AVAILABLE",
                    f"{snap.rows} rows, {len(snap.columns or ())} columns",
                )
            except SourceError as e:
                status_value, detail = e.status.value, str(e)
            except Exception as e:  # noqa: BLE001 - a status check must survive one bad adapter
                status_value, detail = "ERROR", repr(e)
            record_health(
                con,
                SourceHealth(adapter.name, dataset, SourceStatus(status_value), checked_at, detail),
            )
            style = {
                "AVAILABLE": "green",
                "BLOCKED_BY_POLICY": "yellow",
                "NO_CREDENTIALS": "yellow",
                "NOT_FOUND": "yellow",
                "ERROR": "red",
            }.get(status_value, "")
            table.add_row(adapter.name, dataset, f"[{style}]{status_value}[/{style}]", detail)
            if status_value == "ERROR":
                exit_code = 1

    console.print(table)
    con.close()
    if exit_code:
        raise typer.Exit(code=exit_code)


@sources_app.command("ingest")
def sources_ingest(
    season_start: int = typer.Option(2020, help="First season to ingest for seasonal datasets"),
    season_end: int = typer.Option(2026, help="Last season to ingest for seasonal datasets"),
    include_blocked: bool = typer.Option(
        False, help="Also health-check sleeper/fantasypros/cfbd (expected to be blocked here)"
    ),
) -> None:
    """Fetch and snapshot every dataset from the available sources across the given season
    range. Non-seasonal datasets (players, IDs, combine, etc.) are fetched once. A season
    that doesn't exist upstream yet is recorded NOT_FOUND, never fabricated.

    For the full historical backfill used by baseline/ML training, widen the range, e.g.
    `alpha-squad sources ingest --season-start 1999 --season-end 2025`.
    """
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    adapters = {a.name: a for a in all_adapters(settings)}

    results: list[tuple[str, str, dict, str, str]] = []

    def _try_fetch(source_name: str, dataset: str, params: dict) -> None:
        adapter = adapters[source_name]
        try:
            snap = adapter.fetch(dataset, **params)
            record_snapshot(con, snap)
            results.append((source_name, dataset, params, "OK", f"{snap.rows} rows"))
        except SourceError as e:
            results.append((source_name, dataset, params, e.status.value, str(e)))
        except Exception as e:  # noqa: BLE001 - ingestion must survive a single bad fetch
            results.append((source_name, dataset, params, "ERROR", repr(e)))

    for source_name, datasets in _NON_SEASONAL.items():
        for ds in datasets:
            _try_fetch(source_name, ds, {})

    for source_name, datasets in _SEASONAL.items():
        for ds in datasets:
            for season in range(season_start, season_end + 1):
                _try_fetch(source_name, ds, {"season": season})

    if include_blocked:
        for source_name in ("sleeper", "fantasypros", "cfbd"):
            for health in adapters[source_name].health():
                record_health(con, health)
                results.append(
                    (source_name, health.dataset, {}, health.status.value, health.detail)
                )

    table = Table(title="Ingestion results")
    for col in ("source", "dataset", "params", "status", "detail"):
        table.add_column(col)
    counts: dict[str, int] = {}
    for source_name, dataset, params, status, detail in results:
        counts[status] = counts.get(status, 0) + 1
        style = {"OK": "green", "NOT_FOUND": "dim"}.get(
            status, "yellow" if status != "ERROR" else "red"
        )
        table.add_row(
            source_name, dataset, str(params) or "-", f"[{style}]{status}[/{style}]", detail
        )
    console.print(table)
    console.print(f"Summary: {counts}")
    con.close()


@identity_app.command("build")
def identity_build() -> None:
    """Build/refresh the canonical player identity spine and crosswalk from the latest
    stored snapshots (run `sources ingest` first if none exist). Idempotent: safe to
    re-run after new snapshots land."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    try:
        report = build_identity(con, settings)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        con.close()
        raise typer.Exit(code=1) from e

    console.print(f"players upserted: [green]{report.players_upserted}[/green]")
    table = Table(title="ID mappings")
    for col in ("id_type", "inserted", "collisions_quarantined"):
        table.add_column(col)
    for m in report.mapping_results:
        table.add_row(m.id_type, str(m.inserted), str(m.collisions_quarantined))
    console.print(table)
    console.print(f"identity exceptions on file: [yellow]{report.exceptions_recorded}[/yellow]")
    con.close()


@identity_app.command("exceptions")
def identity_exceptions(
    status: str = typer.Option(None, help="Filter by status: PENDING, RESOLVED, UNSUPPORTED"),
) -> None:
    """List quarantined identity mappings awaiting resolution."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    rows = list_exceptions(con, status=status)
    table = Table(title=f"Identity exceptions{f' ({status})' if status else ''}")
    for col in ("exception_id", "exception_type", "status", "subject", "detected_at"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["exception_id"], r["exception_type"], r["status"], r["subject"], str(r["detected_at"])
        )
    console.print(table)
    console.print(f"total: {len(rows)}")
    con.close()


@features_app.command("build")
def features_build(
    season_start: int = typer.Option(
        2012, help="First season (snap_counts, an input, starts 2012)"
    ),
    season_end: int = typer.Option(2026, help="Last season to include"),
) -> None:
    """Build the games/player_week_stats/player_week_features tables from stored snapshots
    for the given season range. Requires `sources ingest` and `identity build` to have
    already run for that range."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    seasons = list(range(season_start, season_end + 1))
    try:
        report = build_features(con, settings, seasons)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        con.close()
        raise typer.Exit(code=1) from e

    console.print(f"games inserted: [green]{report.games_inserted}[/green]")
    console.print(f"player_week_stats upserted: [green]{report.player_week_stats_upserted}[/green]")
    console.print(
        f"player_week_features upserted: [green]{report.player_week_features_upserted}[/green]"
    )
    console.print(
        f"player_season_stats upserted: [green]{report.player_season_stats_upserted}[/green]"
    )
    console.print(f"team_week_stats upserted: [green]{report.team_week_stats_upserted}[/green]")
    console.print(
        f"team_week_features upserted: [green]{report.team_week_features_upserted}[/green]"
    )
    console.print(
        f"player panel rows with team features attached: [green]{report.player_panel_team_attached}[/green]"
    )
    con.close()


@market_app.command("build")
def market_build() -> None:
    """Build market_snapshot from the stored DynastyProcess fp_ecr_history snapshot
    (redraft-overall/1QB ECR)."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    try:
        n = build_market_snapshot(con, settings)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        con.close()
        raise typer.Exit(code=1) from e
    console.print(f"market_snapshot rows upserted: [green]{n}[/green]")
    con.close()


@evaluate_app.command("baselines")
def evaluate_baselines(
    season_start: int = typer.Option(2016, help="First target season to evaluate"),
    season_end: int = typer.Option(2025, help="Last target season to evaluate"),
    report_path: str = typer.Option(
        "reports/baseline_evaluation.md", help="Markdown report output path"
    ),
) -> None:
    """Walk-forward evaluate every registered baseline (previous-year, weighted-2yr,
    ECR-implied) against real outcomes for each season, and publish a report. Requires
    `features build` and `market build` to have already run for the relevant seasons."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    seasons = list(range(season_start, season_end + 1))
    results = run_baselines(con, seasons)

    table = Table(title="Baseline evaluation (ALL positions)")
    for col in (
        "model",
        "season",
        "n",
        "mae",
        "rmse",
        "spearman",
        "top12_hit",
        "top24_hit",
        "tier_acc",
    ):
        table.add_column(col)
    for m in results:
        if m.position != "ALL":
            continue
        table.add_row(
            m.model_name,
            str(m.season),
            str(m.n),
            f"{m.mae:.2f}" if m.mae == m.mae else "-",
            f"{m.rmse:.2f}" if m.rmse == m.rmse else "-",
            f"{m.spearman:.3f}" if m.spearman == m.spearman else "-",
            f"{m.top12_hit_rate:.2f}" if m.top12_hit_rate is not None else "-",
            f"{m.top24_hit_rate:.2f}" if m.top24_hit_rate is not None else "-",
            f"{m.tier_accuracy:.2f}" if m.tier_accuracy is not None else "-",
        )
    console.print(table)

    write_evaluation_report(con, Path(report_path))
    console.print(f"report written to [green]{report_path}[/green]")
    con.close()


@train_app.command("established")
def train_established(
    season_start: int = typer.Option(2020, help="First target season to walk-forward evaluate"),
    season_end: int = typer.Option(2025, help="Last target season to walk-forward evaluate"),
    min_train_season: int = typer.Option(2015, help="Earliest season usable for training data"),
    report_path: str = typer.Option(
        "reports/established_ml_evaluation.md", help="Markdown report output path"
    ),
) -> None:
    """Walk-forward train and evaluate established-player ML (Ridge, CatBoost, XGBoost,
    opportunity-only, team-environment-only, and an ensemble) per position, comparing
    against the M4 baselines through the same evaluation harness. Requires `features build`
    and `market build` to have already run for the relevant seasons."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    run_report = run_established_ml(con, season_start, season_end, min_train_season)

    table = Table(title="Established-player ML evaluation (ALL positions per model/season)")
    for col in ("model", "season", "n", "mae", "rmse", "spearman", "top12_hit", "top24_hit"):
        table.add_column(col)
    for m in run_report.metrics:
        table.add_row(
            m.model_name,
            str(m.season),
            str(m.n),
            f"{m.mae:.2f}" if m.mae == m.mae else "-",
            f"{m.rmse:.2f}" if m.rmse == m.rmse else "-",
            f"{m.spearman:.3f}" if m.spearman == m.spearman else "-",
            f"{m.top12_hit_rate:.2f}" if m.top12_hit_rate is not None else "-",
            f"{m.top24_hit_rate:.2f}" if m.top24_hit_rate is not None else "-",
        )
    console.print(table)
    if run_report.skipped:
        console.print(f"[yellow]skipped: {run_report.skipped}[/yellow]")

    write_evaluation_report(con, Path(report_path))
    console.print(f"report written to [green]{report_path}[/green]")
    con.close()


@train_app.command("established-season")
def train_established_season(
    season_start: int = typer.Option(2020, help="First target season to walk-forward evaluate"),
    season_end: int = typer.Option(2025, help="Last target season to walk-forward evaluate"),
    min_train_season: int = typer.Option(2015, help="Earliest season usable for training data"),
    report_path: str = typer.Option(
        "reports/established_ml_evaluation.md", help="Markdown report output path"
    ),
) -> None:
    """Walk-forward train and evaluate season-level (preseason) established-player ML —
    the genuine apples-to-apples comparison against M4's baselines, since both use only
    information available before the target season starts (unlike `train established`,
    which additionally uses the target season's own in-progress weeks)."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    run_report = run_season_level_established_ml(con, season_start, season_end, min_train_season)

    table = Table(title="Season-level (preseason) established-player ML evaluation")
    for col in ("model", "season", "n", "mae", "rmse", "spearman", "top12_hit", "top24_hit"):
        table.add_column(col)
    for m in run_report.metrics:
        table.add_row(
            m.model_name,
            str(m.season),
            str(m.n),
            f"{m.mae:.2f}" if m.mae == m.mae else "-",
            f"{m.rmse:.2f}" if m.rmse == m.rmse else "-",
            f"{m.spearman:.3f}" if m.spearman == m.spearman else "-",
            f"{m.top12_hit_rate:.2f}" if m.top12_hit_rate is not None else "-",
            f"{m.top24_hit_rate:.2f}" if m.top24_hit_rate is not None else "-",
        )
    console.print(table)
    if run_report.skipped:
        console.print(f"[yellow]skipped: {run_report.skipped}[/yellow]")

    write_evaluation_report(con, Path(report_path))
    console.print(f"report written to [green]{report_path}[/green]")
    con.close()


@train_app.command("uncertainty")
def train_uncertainty(
    season_start: int = typer.Option(2020, help="First target season to walk-forward evaluate"),
    season_end: int = typer.Option(2025, help="Last target season to walk-forward evaluate"),
    min_train_season: int = typer.Option(2015, help="Earliest season usable for training data"),
    report_path: str = typer.Option("reports/calibration_report.md", help="Markdown report output path"),
) -> None:
    """Walk-forward split-conformal uncertainty: p10-p90 + top-12/24 probabilities per
    player/season/position, with out-of-sample calibration diagnostics (did the intervals
    actually contain that fraction of real outcomes?)."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    run_report = run_uncertainty(con, season_start, season_end, min_train_season)

    table = Table(title="Calibration diagnostics (out-of-sample coverage)")
    for col in ("season", "position", "n", "coverage_10_90 (target 0.80)", "coverage_25_75 (target 0.50)", "mean_width"):
        table.add_column(col)
    for row in run_report.calibration_rows:
        if row.get("n", 0) == 0:
            continue
        table.add_row(
            str(row["season"]), row["position"], str(row["n"]),
            f"{row['coverage_10_90']:.2f}", f"{row['coverage_25_75']:.2f}",
            f"{row['mean_interval_width_10_90']:.1f}",
        )
    console.print(table)
    console.print(f"predictions written: [green]{run_report.predictions_written}[/green]")
    if run_report.skipped:
        console.print(f"[yellow]skipped: {run_report.skipped}[/yellow]")

    lines = [
        "# Uncertainty Calibration Report",
        "",
        "Out-of-sample: season S's intervals are calibrated on season S-1's residuals from a "
        "model trained on seasons before S-1, then checked against season S's real outcomes "
        "that the model/calibration never saw. coverage_10_90 should be near 0.80; "
        "coverage_25_75 near 0.50. See docs/DECISIONS.md for the conformal method.",
        "",
        "| season | position | n | coverage_10_90 | coverage_25_75 | mean_width_10_90 |",
        "|---|---|---|---|---|---|",
    ]
    for row in run_report.calibration_rows:
        if row.get("n", 0) == 0:
            continue
        lines.append(
            f"| {row['season']} | {row['position']} | {row['n']} | "
            f"{row['coverage_10_90']:.3f} | {row['coverage_25_75']:.3f} | "
            f"{row['mean_interval_width_10_90']:.2f} |"
        )
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text("\n".join(lines) + "\n")
    console.print(f"report written to [green]{report_path}[/green]")
    con.close()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
