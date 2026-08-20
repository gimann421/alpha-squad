"""Alpha Squad CLI entry point. `uv run alpha-squad --help` for the full command tree."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from alpha_squad.config.settings import get_settings
from alpha_squad.identity.canonical import build_identity
from alpha_squad.identity.exceptions import list_exceptions
from alpha_squad.sources.base import SourceError, SourceHealth, SourceStatus, utcnow
from alpha_squad.sources.registry import all_adapters
from alpha_squad.storage.db import get_connection, init_db
from alpha_squad.storage.snapshots import record_health, record_snapshot

app = typer.Typer(help="Alpha Squad — fantasy football market-inefficiency intelligence system")
sources_app = typer.Typer(help="Data source operations")
identity_app = typer.Typer(help="Canonical player identity operations")
app.add_typer(sources_app, name="sources")
app.add_typer(identity_app, name="identity")
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
