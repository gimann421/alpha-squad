"""Alpha Squad CLI entry point. `uv run alpha-squad --help` for the full command tree."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from alpha_squad.agents.contracts import Task
from alpha_squad.agents.disagreement import (
    detect_baseline_vs_ml_disagreements,
    detect_model_vs_market_disagreements,
    resolve_and_record,
)
from alpha_squad.agents.orchestrator import run_pipeline
from alpha_squad.agents.state import reconstruct_run
from alpha_squad.config.settings import get_settings
from alpha_squad.evidence.events import build_evidence_events_range
from alpha_squad.evidence.prior_update import run_prior_update
from alpha_squad.evidence.sleeper_trending import detect_sleeper_trending
from alpha_squad.features.build import build_features
from alpha_squad.features.college_production import (
    build_college_usage,
    seasons_needed_for_rookies,
)
from alpha_squad.identity.canonical import build_identity
from alpha_squad.identity.exceptions import list_exceptions
from alpha_squad.league.context import DEFAULT_LEAGUE_ID, list_registered_leagues, resolve_league
from alpha_squad.league.decisions import record_decision
from alpha_squad.league.draft import recommend_draft_pick
from alpha_squad.league.replacement import (
    load_season_projections,
    positional_scarcity,
    replacement_level,
)
from alpha_squad.league.trade import recommend_dynasty_trade
from alpha_squad.league.waiver import recommend_waiver_pickup
from alpha_squad.market.consensus import build_live_fantasypros_snapshot, build_market_snapshot
from alpha_squad.market.dynasty_values import build_dynasty_values
from alpha_squad.market.edge import (
    DEFAULT_ECR_TYPE,
    evaluate_historical_edge,
    run_edge_build,
    write_edge_validation_report,
)
from alpha_squad.models.baselines.run import run_baselines
from alpha_squad.models.established.season_level import run_season_level_established_ml
from alpha_squad.models.established.train import run_established_ml
from alpha_squad.models.report import write_evaluation_report
from alpha_squad.models.rookie.ablation import compare_arms, write_ablation_report
from alpha_squad.models.rookie.features import COLLEGE_FEATURE_VERSION, FEATURES_WITH_COLLEGE
from alpha_squad.models.rookie.train import run_rookie_models
from alpha_squad.models.simulation.correlated import (
    MIN_TEAM_WEEKS,
    record_simulation_run,
    simulate_team_season,
)
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
edge_app = typer.Typer(help="Model-vs-market EDGE operations")
evidence_app = typer.Typer(help="Structured evidence engine operations")
league_app = typer.Typer(help="League-specific decision engine operations")
orchestrate_app = typer.Typer(help="Agent orchestrator operations")
simulate_app = typer.Typer(help="Team-season Monte Carlo simulation operations")
app.add_typer(sources_app, name="sources")
app.add_typer(identity_app, name="identity")
app.add_typer(features_app, name="features")
app.add_typer(market_app, name="market")
app.add_typer(evaluate_app, name="evaluate")
app.add_typer(train_app, name="train")
app.add_typer(edge_app, name="edge")
app.add_typer(evidence_app, name="evidence")
app.add_typer(league_app, name="league")
app.add_typer(orchestrate_app, name="orchestrate")
app.add_typer(simulate_app, name="simulate")
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
        False,
        help="Also health-check sleeper/fantasypros/cfbd (all three now genuinely AVAILABLE, "
        "D31/D36/D37; they are health-checked rather than bulk-ingested here)",
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
    console.print(f"combine_results upserted: [green]{report.combine_results_upserted}[/green]")
    console.print(f"rookie_features upserted: [green]{report.rookie_features_upserted}[/green]")
    con.close()


@features_app.command("build-college-usage")
def features_build_college_usage() -> None:
    """Ingest CFBD player_usage (D38) for every college season a rookie already in `players`
    needs (their final college season, rookie_season - 1), and upsert into `college_usage`,
    espn_id-bridged. Run `features build` afterward so rookie_features picks up the join;
    requires CFBD_API_KEY and `identity build` having already populated player_id_map."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    seasons = seasons_needed_for_rookies(con)
    if not seasons:
        console.print("[yellow]no rookies in `players` yet -- run `identity build` first[/yellow]")
        con.close()
        return
    try:
        n = build_college_usage(con, settings, seasons)
    except (RuntimeError, SourceError) as e:
        console.print(f"[red]{e}[/red]")
        con.close()
        raise typer.Exit(code=1) from e
    console.print(f"seasons ingested: [green]{seasons}[/green]")
    console.print(f"college_usage rows upserted: [green]{n}[/green]")
    con.close()


@market_app.command("build")
def market_build() -> None:
    """Build market_snapshot from the stored DynastyProcess fp_ecr_history snapshot
    (redraft/dynasty, 1QB and 2QB-superflex ECR series: ro/do/rsf/dsf)."""
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


@market_app.command("capture-live-fantasypros")
def market_capture_live_fantasypros(season: int = 2026) -> None:
    """Capture today's FantasyPros consensus rankings directly from the live API into
    market_snapshot (source='fantasypros_live', D38) -- a separate, provenance-tagged series
    from the DynastyProcess-sourced 'build' command above; requires FANTASYPROS_API_KEY."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    try:
        n = build_live_fantasypros_snapshot(con, settings, season=season)
    except (RuntimeError, SourceError) as e:
        console.print(f"[red]{e}[/red]")
        con.close()
        raise typer.Exit(code=1) from e
    console.print(f"market_snapshot (fantasypros_live) rows upserted: [green]{n}[/green]")
    con.close()


@market_app.command("build-dynasty-values")
def market_build_dynasty_values() -> None:
    """Normalize DynastyProcess's values-players.csv (current 1QB/2QB dynasty value and ECR)
    into dynasty_values."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    try:
        n = build_dynasty_values(con, settings)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        con.close()
        raise typer.Exit(code=1) from e
    console.print(f"dynasty_values rows upserted: [green]{n}[/green]")
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
    report_path: str = typer.Option(
        "reports/calibration_report.md", help="Markdown report output path"
    ),
) -> None:
    """Walk-forward split-conformal uncertainty: p10-p90 + top-12/24 probabilities per
    player/season/position, with out-of-sample calibration diagnostics (did the intervals
    actually contain that fraction of real outcomes?)."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    run_report = run_uncertainty(con, season_start, season_end, min_train_season)

    table = Table(title="Calibration diagnostics (out-of-sample coverage)")
    for col in (
        "season",
        "position",
        "n",
        "coverage_10_90 (target 0.80)",
        "coverage_25_75 (target 0.50)",
        "mean_width",
    ):
        table.add_column(col)
    for row in run_report.calibration_rows:
        if row.get("n", 0) == 0:
            continue
        table.add_row(
            str(row["season"]),
            row["position"],
            str(row["n"]),
            f"{row['coverage_10_90']:.2f}",
            f"{row['coverage_25_75']:.2f}",
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


def _run_rookie_ablation(
    con,
    baseline_report,
    class_start: int,
    class_end: int,
    min_train_class: int,
    report_path: Path,
) -> None:
    """Trains the candidate (+college) feature set over the *same* walk-forward folds as the
    just-run production baseline, prints the delta, and publishes the report
    (docs/DECISIONS.md D39). Distinct model names/feature_version keep both arms' rows in
    evaluation_results/classification_results instead of one silently overwriting the other."""
    candidate_report = run_rookie_models(
        con,
        class_start,
        class_end,
        min_train_class,
        features=FEATURES_WITH_COLLEGE,
        feature_version=COLLEGE_FEATURE_VERSION,
        model_suffix="_college",
    )

    comparisons, n_reg, n_clf = compare_arms(baseline_report, candidate_report)

    table = Table(title="Ablation: +college vs baseline, identical folds")
    for col in ("metric", "baseline", "+college", "delta", "better"):
        table.add_column(col)
    for c in comparisons:
        color = (
            "green" if c.winner == "+college" else ("red" if c.winner == "baseline" else "yellow")
        )
        direction = "higher better" if c.higher_is_better else "lower better"
        table.add_row(
            f"{c.label} ({direction})",
            f"{c.baseline:.4f}",
            f"{c.candidate:.4f}",
            f"{c.delta:+.4f}",
            f"[{color}]{c.winner}[/{color}]",
        )
    console.print(table)
    console.print(f"[dim]paired folds: {n_reg} regression, {n_clf} classification[/dim]")

    result = write_ablation_report(
        con,
        baseline_report,
        candidate_report,
        report_path,
        class_start=class_start,
        class_end=class_end,
        min_train_class=min_train_class,
    )
    console.print(f"\n[bold]{result}[/bold]")
    console.print(f"report written to [green]{report_path}[/green]")


@train_app.command("rookie")
def train_rookie(
    class_start: int = typer.Option(2018, help="First draft class to walk-forward evaluate"),
    class_end: int = typer.Option(2025, help="Last draft class to walk-forward evaluate"),
    min_train_class: int = typer.Option(2000, help="Earliest draft class usable for training data"),
    ablation: bool = typer.Option(
        False,
        "--ablation",
        help="Also train the candidate feature set that adds CFBD college production, over "
        "identical folds, and print a side-by-side delta against the production baseline",
    ),
    report_path: str = typer.Option(
        "reports/rookie_college_production_ablation.md",
        help="Where --ablation writes its markdown report",
    ),
) -> None:
    """Walk-forward rookie regression (rookie-year PPR points) and breakout classification
    (top-24-at-position), strictly by draft class. Feature set is draft capital + combine +
    landing spot (D20). CFBD college usage share (D38) was measured and NOT adopted -- it was
    neutral-to-slightly-worse on every metric (D39, reports/rookie_college_production_ablation.md);
    re-measure any time with --ablation. Requires `features build` to have already populated
    rookie_features."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    run_report = run_rookie_models(con, class_start, class_end, min_train_class)

    if ablation:
        _run_rookie_ablation(
            con, run_report, class_start, class_end, min_train_class, Path(report_path)
        )

    table = Table(title="Rookie regression (ALL positions per class)")
    for col in ("model", "class", "n", "mae", "rmse", "spearman"):
        table.add_column(col)
    for m in run_report.regression_metrics:
        table.add_row(
            m.model_name,
            str(m.season),
            str(m.n),
            f"{m.mae:.2f}" if m.mae == m.mae else "-",
            f"{m.rmse:.2f}" if m.rmse == m.rmse else "-",
            f"{m.spearman:.3f}" if m.spearman == m.spearman else "-",
        )
    console.print(table)

    table2 = Table(title="Rookie breakout classification (per position/class)")
    for col in ("model", "class", "position", "n", "brier", "accuracy", "base_rate"):
        table2.add_column(col)
    for c in run_report.classification_metrics:
        if c.n == 0:
            continue
        table2.add_row(
            c.model_name,
            str(c.cohort),
            c.position,
            str(c.n),
            f"{c.brier_score:.3f}",
            f"{c.accuracy:.2f}",
            f"{c.base_rate:.2f}",
        )
    console.print(table2)
    if run_report.skipped:
        console.print(f"[yellow]skipped: {run_report.skipped}[/yellow]")
    con.close()


@edge_app.command("build")
def edge_build(
    season_start: int = typer.Option(2021, help="First target season to build EDGE for"),
    season_end: int = typer.Option(2025, help="Last target season to build EDGE for"),
    ecr_type: str = typer.Option(
        DEFAULT_ECR_TYPE, help="Market series to compare against (rsf=redraft-superflex/2QB)"
    ),
) -> None:
    """Build model-vs-market EDGE (rank/points/probability edge, BUY/HOLD/SELL/WATCH) for
    each season, gated so a raw ranking discrepancy alone can never produce BUY/SELL
    (ACCEPTANCE_CRITERIA.md). Requires `market build` and `train uncertainty` to have already
    run for the relevant seasons."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    report = run_edge_build(con, season_start, season_end, ecr_type)

    table = Table(title=f"EDGE actions built (ecr_type={ecr_type})")
    for col in ("season", "action", "n"):
        table.add_column(col)
    action_counts = con.execute(
        """
        SELECT season, action, count(*) FROM edge_snapshot
        WHERE ecr_type = ? AND season BETWEEN ? AND ?
        GROUP BY 1, 2 ORDER BY 1, 2
        """,
        [ecr_type, season_start, season_end],
    ).fetchall()
    for season, action, n in action_counts:
        table.add_row(str(season), action, str(n))
    console.print(table)
    console.print(
        f"edges written: [green]{report.edges_written}[/green] across seasons {report.seasons}"
    )
    if report.skipped:
        console.print(f"[yellow]skipped: {report.skipped}[/yellow]")
    con.close()


@edge_app.command("validate")
def edge_validate(
    season_start: int = typer.Option(2021, help="First season to validate"),
    season_end: int = typer.Option(2025, help="Last season to validate"),
    ecr_type: str = typer.Option(DEFAULT_ECR_TYPE, help="Market series EDGE was built against"),
    report_path: str = typer.Option(
        "reports/edge_validation.md", help="Markdown report output path"
    ),
) -> None:
    """Historically validate EDGE: did BUY/SELL cohorts actually beat market expectation?
    Published either way. Requires `edge build` to have already run for these seasons."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    results = evaluate_historical_edge(con, season_start, season_end, ecr_type)

    table = Table(title="Historical EDGE validation")
    for col in (
        "season",
        "action",
        "n",
        "mean_actual_pts",
        "mean_market_implied_pts",
        "mean_outperformance",
    ):
        table.add_column(col)
    for r in results:
        table.add_row(
            str(r["season"]),
            r["action"],
            str(r["n"]),
            f"{r['mean_actual_points']:.2f}" if r["mean_actual_points"] is not None else "-",
            f"{r['mean_market_implied_points']:.2f}"
            if r["mean_market_implied_points"] is not None
            else "-",
            f"{r['mean_outperformance_vs_market']:.2f}"
            if r["mean_outperformance_vs_market"] is not None
            else "-",
        )
    console.print(table)

    write_edge_validation_report(con, Path(report_path))
    console.print(f"report written to [green]{report_path}[/green]")
    con.close()


@evidence_app.command("build")
def evidence_build(
    season_start: int = typer.Option(2019, help="First season to detect evidence events for"),
    season_end: int = typer.Option(2025, help="Last season to detect evidence events for"),
) -> None:
    """Detect structured evidence events (depth-chart moves, injury reports, roster
    transactions, usage-share shifts) from officially-sourced nflverse data. Requires
    `sources ingest` for depth_charts/injuries/weekly_rosters and `features build` to have
    already run for the relevant seasons."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    report = build_evidence_events_range(con, season_start, season_end)

    table = Table(title="Evidence events detected")
    table.add_column("event_type")
    table.add_column("n")
    for event_type, n in sorted(report.by_type.items()):
        table.add_row(event_type, str(n))
    console.print(table)
    console.print(f"total events written: [green]{report.events_written}[/green]")
    if report.skipped:
        console.print(f"[yellow]skipped: {report.skipped}[/yellow]")
    con.close()


@evidence_app.command("update-projections")
def evidence_update_projections(
    season: int = typer.Option(..., help="Season to apply evidence-driven projection deltas for"),
    week: int = typer.Option(..., help="Week to apply evidence-driven projection deltas for"),
) -> None:
    """Apply the bounded, explainable evidence adjustment to that week's real weekly
    established-ML projections (never overwrites the base prediction; writes a separate
    projection_deltas row with reason + evidence_ids). Requires `train established` to have
    already populated weekly_projection_snapshot and `evidence build` to have run."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    deltas = run_prior_update(con, season, week)

    table = Table(title=f"Evidence-adjusted projections ({season} week {week})")
    for col in ("player_id", "base", "adjusted", "adjustment_pct", "evidence_score"):
        table.add_column(col)
    for d in sorted(deltas, key=lambda d: -abs(d.adjustment_pct))[:20]:
        table.add_row(
            d.player_id,
            f"{d.base_value:.2f}",
            f"{d.adjusted_value:.2f}",
            f"{d.adjustment_pct:+.1%}",
            f"{d.evidence_score:.2f}",
        )
    console.print(table)
    n_adjusted = sum(1 for d in deltas if abs(d.adjustment_pct) > 1e-9)
    console.print(
        f"deltas written: [green]{len(deltas)}[/green] ({n_adjusted} materially adjusted)"
    )
    con.close()


@evidence_app.command("build-sleeper-trending")
def evidence_build_sleeper_trending(
    season: int = typer.Option(..., help="Season this evidence should inform"),
    week: int = typer.Option(
        1, help="Week this evidence should inform (1 = preseason/entering the season)"
    ),
) -> None:
    """Real-time Sleeper community add/drop momentum as Weak-tier evidence
    (docs/DECISIONS.md D31/D32) -- unlike `evidence build`'s Strong-tier detectors, this
    fetches live (Sleeper's trending endpoints have no historical lookback) and always
    reflects activity as of right now, attributed to whichever (season, week) you say it
    should inform. Requires `identity build` to have run (joins via DynastyProcess's
    sleeper_id crosswalk)."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    try:
        n = detect_sleeper_trending(con, settings, season, week)
    except SourceError as e:
        console.print(f"[red]{e}[/red]")
        con.close()
        raise typer.Exit(code=1) from e

    console.print(f"sleeper trending events written: [green]{n}[/green]")
    con.close()


@league_app.command("list")
def league_list() -> None:
    """List every registered league (config/league_configs/registry.yaml) -- the seamless
    "which league am I about to run this for" check before any draft/waiver/trade/replacement
    command. Add a league by editing that file: a `source: yaml` entry points at a local
    config, a `source: sleeper` entry is hydrated live from a real Sleeper league on every
    use (docs/DECISIONS.md D33)."""
    registry = list_registered_leagues()
    if not registry:
        console.print(
            "[yellow]no leagues registered in config/league_configs/registry.yaml[/yellow]"
        )
        return

    table = Table(title="Registered leagues")
    for col in ("league_id", "source", "detail"):
        table.add_column(col)
    for league_id, entry in sorted(registry.items()):
        source = entry.get("source", "?")
        detail = entry.get("path") if source == "yaml" else entry.get("sleeper_league_id")
        table.add_row(league_id, source, str(detail))
    console.print(table)


@league_app.command("replacement")
def league_replacement(
    season: int = typer.Option(..., help="Season to compute replacement level/scarcity for"),
    league: str = typer.Option(
        DEFAULT_LEAGUE_ID, help="Registered league id to use (see `alpha-squad league list`)"
    ),
) -> None:
    """Show replacement level and positional scarcity derived from the league's own lineup
    config -- e.g. a 2QB league's QB replacement level sits far deeper than a 1QB league's,
    purely from the config, not a hardcoded assumption. Requires `train uncertainty` to have
    already run for this season."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    league = resolve_league(league, con=con, settings=settings)
    projections, positions = load_season_projections(con, season)
    if not projections:
        console.print(
            f"[red]no uncertainty_predictions for season {season}; run `train uncertainty` first[/red]"
        )
        con.close()
        raise typer.Exit(code=1)
    levels = replacement_level(league, projections, positions)
    scarcity = positional_scarcity(league, projections, positions)

    table = Table(title=f"Replacement level & scarcity ({league.league_id}, {season})")
    for col in ("position", "replacement_level", "scarcity"):
        table.add_column(col)
    for pos in sorted(levels):
        table.add_row(pos, f"{levels[pos]:.1f}", f"{scarcity.get(pos, 0.0):.1f}")
    console.print(table)
    con.close()


@league_app.command("draft")
def league_draft(
    season: int = typer.Option(..., help="Season to recommend a draft pick for"),
    roster: str = typer.Option(
        "", help="Comma-separated positions already on your roster, e.g. 'QB,RB,RB'"
    ),
    available: str = typer.Option(
        "", help="Comma-separated player_ids available to draft (default: every projected player)"
    ),
    next_pick: int | None = typer.Option(
        None, help="Your next overall pick number, for survival probability"
    ),
    ecr_type: str = typer.Option(DEFAULT_ECR_TYPE, help="Market series for survival probability"),
    league: str = typer.Option(
        DEFAULT_LEAGUE_ID, help="Registered league id to use (see `alpha-squad league list`)"
    ),
    top_n: int = typer.Option(5, help="Number of alternatives to show"),
) -> None:
    """Recommend a draft pick: VORP, roster fit, model confidence, and next-pick survival
    probability, with alternatives and reasoning (AGENT_CONTRACTS.md's Decision contract)."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    league = resolve_league(league, con=con, settings=settings)
    roster_positions = [p.strip() for p in roster.split(",") if p.strip()]
    if available:
        available_ids = {p.strip() for p in available.split(",") if p.strip()}
    else:
        projections, _ = load_season_projections(con, season)
        available_ids = set(projections)

    try:
        rec = recommend_draft_pick(
            con, league, season, roster_positions, available_ids, next_pick, ecr_type, top_n
        )
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        con.close()
        raise typer.Exit(code=1) from e

    table = Table(title="Draft recommendation")
    for col in ("player_id", "position", "vorp", "confidence", "survival_prob", "score"):
        table.add_column(col)
    for c in rec.candidates:
        table.add_row(
            c.player_id,
            c.position,
            f"{c.vorp:+.1f}",
            f"{c.confidence:.2f}" if c.confidence is not None else "-",
            f"{c.survival_probability:.0%}" if c.survival_probability is not None else "-",
            f"{c.score:.1f}",
        )
    console.print(table)
    console.print(f"[green]Recommendation: {rec.recommendation}[/green]")
    for r in rec.reasons:
        console.print(f"  - {r}")

    decision_id = record_decision(
        con,
        "draft_pick",
        league.league_id,
        season,
        rec.recommendation,
        rec.alternatives,
        rec.expected_value,
        rec.confidence,
        rec.reasons,
        {"league": league.league_id, "ecr_type": ecr_type, "next_pick": next_pick},
    )
    console.print(f"decision recorded: [green]{decision_id}[/green]")
    con.close()


@league_app.command("waiver")
def league_waiver(
    season: int = typer.Option(..., help="Season"),
    week: int = typer.Option(..., help="Week"),
    player_id: str = typer.Option(..., help="Canonical player_id to evaluate for a waiver claim"),
    roster: str = typer.Option("", help="Comma-separated positions already on your roster"),
    league: str = typer.Option(
        DEFAULT_LEAGUE_ID, help="Registered league id to use (see `alpha-squad league list`)"
    ),
) -> None:
    """Recommend a FAAB bid for a specific waiver-wire player: meaningful-role probability,
    dynasty value, a value-spike read from recent evidence, roster fit, competing-bid
    likelihood, and a bounded bid recommendation."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    league = resolve_league(league, con=con, settings=settings)
    roster_positions = [p.strip() for p in roster.split(",") if p.strip()]
    try:
        rec = recommend_waiver_pickup(con, league, season, week, player_id, roster_positions)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        con.close()
        raise typer.Exit(code=1) from e

    console.print(
        f"[green]{rec.player_id}[/green] ({rec.position}): recommended FAAB bid "
        f"[green]${rec.recommended_bid:.2f}[/green] of ${league.faab_budget:.0f}"
    )
    for r in rec.reasons:
        console.print(f"  - {r}")

    decision_id = record_decision(
        con,
        "waiver_bid",
        league.league_id,
        season,
        rec.player_id,
        [],
        rec.recommended_bid,
        rec.meaningful_role_probability,
        rec.reasons,
        {"league": league.league_id, "week": week},
    )
    console.print(f"decision recorded: [green]{decision_id}[/green]")
    con.close()


@league_app.command("trade")
def league_trade(
    season: int = typer.Option(..., help="Season"),
    player_id: str = typer.Option(..., help="Canonical player_id to evaluate for a dynasty trade"),
    ecr_type: str = typer.Option(DEFAULT_ECR_TYPE, help="Market series EDGE was built against"),
    league: str = typer.Option(
        DEFAULT_LEAGUE_ID, help="Registered league id to use (see `alpha-squad league list`)"
    ),
) -> None:
    """Recommend a dynasty buy/hold/sell/watch action: real EDGE (M8) + real dynasty market
    value (M8) + a documented age-curve heuristic (docs/DECISIONS.md D25)."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    league = resolve_league(league, con=con, settings=settings)
    rec = recommend_dynasty_trade(con, player_id, season, ecr_type)

    console.print(f"[green]{rec.action}[/green] {rec.player_id}")
    if rec.dynasty_value_2qb is not None:
        console.print(
            f"  dynasty value (2QB): {rec.dynasty_value_2qb:.0f}, "
            f"age-adjusted: {rec.age_adjusted_value:.0f}"
        )
    for r in rec.reasons:
        console.print(f"  - {r}")

    decision_id = record_decision(
        con,
        "dynasty_trade",
        league.league_id,
        season,
        rec.player_id,
        [],
        rec.age_adjusted_value,
        None,
        rec.reasons,
        {"league": league.league_id, "ecr_type": ecr_type},
    )
    console.print(f"decision recorded: [green]{decision_id}[/green]")
    con.close()


@orchestrate_app.command("demo")
def orchestrate_demo(
    run_id: str = typer.Option(..., help="Identifier for this orchestrated run"),
) -> None:
    """Run a small real DAG through the orchestrator: data_engineering (players/draft_picks/
    combine/player_ids) -> player_identity, with real dependency resolution, retry/backoff,
    and state persisted to agent_tasks/agent_results (never an LLM call, D14)."""
    settings = get_settings()
    tasks = [
        Task(
            task_id=f"{run_id}-data",
            agent="data_engineering",
            objective="Ingest identity source datasets",
            depends_on=[],
            params={
                "datasets": [
                    ["nflverse", "players", {}],
                    ["nflverse", "draft_picks", {}],
                    ["nflverse", "combine", {}],
                    ["dynastyprocess", "player_ids", {}],
                ]
            },
        ),
        Task(
            task_id=f"{run_id}-identity",
            agent="player_identity",
            objective="Build canonical player identity from the ingested snapshots",
            depends_on=[f"{run_id}-data"],
        ),
    ]
    report = run_pipeline(settings, run_id, tasks)

    table = Table(title=f"Orchestrated run {run_id}")
    for col in ("task_id", "agent", "status", "confidence"):
        table.add_column(col)
    for task_id in report.order:
        result = report.results[task_id]
        table.add_row(
            task_id,
            result.agent,
            result.status,
            f"{result.confidence:.2f}" if result.confidence is not None else "-",
        )
    console.print(table)
    for task_id in report.order:
        for f in report.results[task_id].findings:
            console.print(f"  [{task_id}] {f}")


@orchestrate_app.command("status")
def orchestrate_status(run_id: str = typer.Option(..., help="Run ID to reconstruct")) -> None:
    """Reconstruct a full run's status purely from agent_tasks/agent_results DB state --
    no chat transcript or in-memory data required."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)
    rebuilt = reconstruct_run(con, run_id)
    if not rebuilt["tasks"]:
        console.print(f"[yellow]no tasks found for run_id={run_id!r}[/yellow]")
        con.close()
        raise typer.Exit(code=1)

    table = Table(title=f"Run {run_id} (reconstructed from state)")
    for col in ("task_id", "agent", "status", "attempt", "depends_on"):
        table.add_column(col)
    for t in rebuilt["tasks"]:
        table.add_row(
            t["task_id"], t["agent"], t["status"], str(t["attempt"]), ",".join(t["depends_on"])
        )
    console.print(table)
    con.close()


@orchestrate_app.command("disagreements")
def orchestrate_disagreements(
    season: int = typer.Option(..., help="Season to detect disagreements for"),
    ecr_type: str = typer.Option(
        DEFAULT_ECR_TYPE, help="Market series for model-vs-market comparison"
    ),
    run_id: str = typer.Option("adhoc", help="Run ID to associate detected disagreements with"),
) -> None:
    """Detect real disagreements (model vs. market from edge_snapshot.rank_edge; baseline vs.
    established-ML from evaluation_results) and resolve+record each, preserving the minority
    position (AGENT_CONTRACTS.md's conflict protocol)."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    disagreements = detect_model_vs_market_disagreements(con, season, ecr_type)
    for position in ("QB", "RB", "WR", "TE"):
        disagreements.extend(detect_baseline_vs_ml_disagreements(con, season, position))

    table = Table(title=f"Disagreements ({season})")
    for col in ("type", "subject", "majority", "minority", "resolution"):
        table.add_column(col)
    for d in disagreements:
        disagreement_id = resolve_and_record(con, run_id, d)
        table.add_row(
            d["disagreement_type"],
            d["subject"],
            f"{d['majority_position']} ({d['majority_value']:.1f})",
            f"{d['minority_position']} ({d['minority_value']:.1f})",
            disagreement_id,
        )
    console.print(table)
    console.print(f"{len(disagreements)} disagreements detected and recorded")
    con.close()


@simulate_app.command("team-season")
def simulate_team_season_cmd(
    team: str = typer.Option(..., help="Team abbreviation, e.g. 'KC'"),
    season: int = typer.Option(..., help="Season to simulate"),
    n_simulations: int = typer.Option(1000, help="Number of Monte Carlo trials"),
    n_weeks: int = typer.Option(17, help="Simulated regular-season weeks"),
    seed: int = typer.Option(42, help="Random seed, for reproducibility"),
) -> None:
    """Correlated team-season Monte Carlo: every trial draws one joint (plays, pass_rate,
    team_points) sample from the team's real historical covariance, and every rostered
    player's simulated weekly points come from that same trial's draw via their real
    opportunity share and efficiency (docs/DECISIONS.md D8, D29). Prints team- and
    player-level floor/ceiling and the empirically measured QB/WR1 stack correlation, and
    persists the team-level summary to `team_simulation_runs`."""
    settings = get_settings()
    con = get_connection(settings)
    init_db(con)

    result = simulate_team_season(con, team, season, n_weeks, n_simulations, seed)
    if result is None:
        console.print(
            f"[red]Not enough real history for {team} before {season} "
            f"(need >= {MIN_TEAM_WEEKS} prior weeks of team_week_stats/team_week_points).[/red]"
        )
        con.close()
        raise typer.Exit(code=1)

    console.print(
        f"[green]{team} {season}[/green]: mean team points "
        f"{result.mean_team_points:.1f} (std {result.std_team_points:.1f}) over "
        f"{result.n_simulations} simulations x {result.n_weeks} weeks"
    )
    corr_str = f"{result.qb_wr1_correlation:.3f}" if result.qb_wr1_correlation is not None else "-"
    same_str = (
        f"{result.same_position_correlation:.3f}"
        if result.same_position_correlation is not None
        else "-"
    )
    console.print(f"qb_wr1_correlation={corr_str}  same_position_correlation={same_str}")

    table = Table(title="Player season-point distribution")
    for col in ("player_id", "position", "mean", "std", "p10", "p50", "p90"):
        table.add_column(col)
    for p in result.players:
        table.add_row(
            p.player_id,
            p.position,
            f"{p.mean_points:.1f}",
            f"{p.std_points:.1f}",
            f"{p.p10:.1f}",
            f"{p.p50:.1f}",
            f"{p.p90:.1f}",
        )
    console.print(table)

    run_id = record_simulation_run(con, result, seed)
    console.print(f"simulation run recorded: [green]{run_id}[/green]")
    con.close()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
