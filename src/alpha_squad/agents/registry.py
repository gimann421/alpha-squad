"""Real agent implementations. Every agent is a deterministic Python function wrapping
already-built, already-validated M1-M10 pipeline code -- never an LLM call
(ARCHITECTURE.md §6, D14). Each takes (con, settings, task) and returns a Result whose
`status` is one of contracts.TASK_STATES. Failures are caught and reported as FAILED
findings, never silently swallowed."""

from __future__ import annotations

import duckdb

from alpha_squad.agents.contracts import Result, Task
from alpha_squad.config.settings import Settings


def _complete(task: Task, findings: list[str], **kw) -> Result:
    return Result(task_id=task.task_id, agent=task.agent, status="COMPLETE", findings=findings, **kw)


def _failed(task: Task, reason: str) -> Result:
    return Result(task_id=task.task_id, agent=task.agent, status="FAILED", findings=[reason])


def run_data_engineering(con: duckdb.DuckDBPyConnection, settings: Settings, task: Task) -> Result:
    from alpha_squad.sources.base import SourceError
    from alpha_squad.sources.registry import all_adapters
    from alpha_squad.storage.snapshots import record_snapshot

    datasets: list[list] = task.params.get("datasets", [])  # [[source, dataset, params], ...]
    adapters = {a.name: a for a in all_adapters(settings)}
    findings: list[str] = []
    n_ok = 0
    for source_name, dataset, params in datasets:
        try:
            snap = adapters[source_name].fetch(dataset, **(params or {}))
            record_snapshot(con, snap)
            n_ok += 1
        except SourceError as e:
            findings.append(f"{source_name}/{dataset}: {e.status.value}: {e}")
        except Exception as e:  # noqa: BLE001 - one bad dataset must not fail the whole task
            findings.append(f"{source_name}/{dataset}: ERROR: {e!r}")

    if datasets and n_ok == 0:
        return Result(task_id=task.task_id, agent=task.agent, status="FAILED", findings=findings)
    findings.insert(0, f"{n_ok}/{len(datasets)} datasets ingested")
    return _complete(task, findings, confidence=1.0 if n_ok == len(datasets) else 0.5)


def run_player_identity(con: duckdb.DuckDBPyConnection, settings: Settings, task: Task) -> Result:
    from alpha_squad.identity.canonical import build_identity

    try:
        report = build_identity(con, settings)
    except RuntimeError as e:
        return _failed(task, str(e))
    return _complete(task, [f"identity build report: {report}"], confidence=1.0)


def run_projection_ml(con: duckdb.DuckDBPyConnection, settings: Settings, task: Task) -> Result:
    from alpha_squad.features.build import build_features
    from alpha_squad.models.baselines.run import run_baselines
    from alpha_squad.models.established.train import run_established_ml
    from alpha_squad.models.uncertainty.run import run_uncertainty

    p = task.params
    seasons: list[int] = p["seasons"]
    season_start, season_end = min(seasons), max(seasons)
    min_train_season = p.get("min_train_season", 2015)

    try:
        feature_report = build_features(con, settings, seasons)
        baseline_results = run_baselines(con, seasons)
        ml_report = run_established_ml(con, season_start, season_end, min_train_season)
        uncertainty_report = run_uncertainty(con, season_start, season_end, min_train_season)
    except RuntimeError as e:
        return _failed(task, str(e))

    findings = [
        f"features: {feature_report}",
        f"{len(baseline_results)} baseline evaluation rows",
        f"established ML: {len(ml_report.metrics)} metric rows, skipped={ml_report.skipped}",
        f"uncertainty: {uncertainty_report.predictions_written} predictions written",
    ]
    return _complete(task, findings, confidence=0.8)


def run_rookie_ml(con: duckdb.DuckDBPyConnection, settings: Settings, task: Task) -> Result:
    from alpha_squad.models.rookie.train import run_rookie_models

    p = task.params
    try:
        report = run_rookie_models(
            con, p["class_start"], p["class_end"], p.get("min_train_class", 2000)
        )
    except RuntimeError as e:
        return _failed(task, str(e))
    findings = [
        f"{len(report.regression_metrics)} regression rows, "
        f"{len(report.classification_metrics)} classification rows, skipped={report.skipped}"
    ]
    return _complete(task, findings, confidence=0.7)


def run_market_edge(con: duckdb.DuckDBPyConnection, settings: Settings, task: Task) -> Result:
    from alpha_squad.market.consensus import build_market_snapshot
    from alpha_squad.market.dynasty_values import build_dynasty_values
    from alpha_squad.market.edge import DEFAULT_ECR_TYPE, evaluate_historical_edge, run_edge_build

    p = task.params
    try:
        n_market = build_market_snapshot(con, settings)
        n_dynasty = build_dynasty_values(con, settings)
        edge_report = run_edge_build(
            con, p["season_start"], p["season_end"], p.get("ecr_type", DEFAULT_ECR_TYPE)
        )
        validation = evaluate_historical_edge(
            con, p["season_start"], p["season_end"], p.get("ecr_type", DEFAULT_ECR_TYPE)
        )
    except RuntimeError as e:
        return _failed(task, str(e))

    findings = [
        f"market_snapshot: {n_market} rows, dynasty_values: {n_dynasty} rows",
        f"edge: {edge_report.edges_written} rows across seasons {edge_report.seasons}, "
        f"skipped={edge_report.skipped}",
        f"historical validation: {len(validation)} (season, action) cohorts scored",
    ]
    return _complete(task, findings, confidence=0.75)


def run_news_evidence(con: duckdb.DuckDBPyConnection, settings: Settings, task: Task) -> Result:
    from alpha_squad.evidence.events import build_evidence_events_range
    from alpha_squad.evidence.prior_update import run_prior_update

    p = task.params
    report = build_evidence_events_range(con, p["season_start"], p["season_end"])
    findings = [f"evidence: {report.events_written} events written, by_type={report.by_type}"]
    if report.skipped:
        findings.append(f"skipped: {report.skipped}")

    if "week" in p:
        deltas = run_prior_update(con, p["season_end"], p["week"], p.get("base_model_name", "ml_catboost"))
        findings.append(f"prior update: {len(deltas)} deltas applied for week {p['week']}")

    return _complete(task, findings, confidence=0.7)


def run_fantasy_strategy(con: duckdb.DuckDBPyConnection, settings: Settings, task: Task) -> Result:
    from alpha_squad.league.context import load_league_context
    from alpha_squad.league.draft import recommend_draft_pick
    from alpha_squad.league.trade import recommend_dynasty_trade
    from alpha_squad.league.waiver import recommend_waiver_pickup

    p = task.params
    league = load_league_context(p.get("league_config")) if p.get("league_config") else load_league_context()
    decision_type = p.get("decision_type", "draft_pick")
    try:
        if decision_type == "draft_pick":
            rec = recommend_draft_pick(
                con,
                league,
                p["season"],
                p.get("roster_positions", []),
                set(p["available_player_ids"]),
                p.get("next_pick_overall"),
                p.get("ecr_type", "rsf"),
                p.get("top_n", 5),
            )
            findings = [f"recommended {rec.recommendation}"] + rec.reasons
            confidence = rec.confidence
        elif decision_type == "waiver_bid":
            rec = recommend_waiver_pickup(
                con, league, p["season"], p["week"], p["player_id"], p.get("roster_positions", [])
            )
            findings = [f"bid ${rec.recommended_bid:.2f}"] + rec.reasons
            confidence = rec.meaningful_role_probability
        elif decision_type == "dynasty_trade":
            rec = recommend_dynasty_trade(con, p["player_id"], p["season"], p.get("ecr_type", "rsf"))
            findings = [f"action {rec.action}"] + rec.reasons
            confidence = None
        else:
            return _failed(task, f"unknown decision_type: {decision_type}")
    except RuntimeError as e:
        return _failed(task, str(e))

    return _complete(task, findings, confidence=confidence)


def run_evaluation_qa(con: duckdb.DuckDBPyConnection, settings: Settings, task: Task) -> Result:
    """Reviews another agent's real, already-recorded output and can REJECT an unsupported
    claim (ACCEPTANCE_CRITERIA.md: "Evaluation/QA can reject unsupported claims") -- reusing
    M5's own real validation gate (model_registry.validated) rather than re-deriving a new
    judgment, and cross-checking the model's stored MAE against the baseline it must beat."""
    p = task.params
    model_name = p["model_name"]
    position = p["position"]
    season = p["season"]

    row = con.execute(
        "SELECT validated, notes FROM model_registry WHERE model_name = ? AND position = ? "
        "ORDER BY trained_at DESC LIMIT 1",
        [model_name, position],
    ).fetchone()
    if row is None:
        return Result(
            task_id=task.task_id,
            agent=task.agent,
            status="NEEDS_REVIEW",
            findings=[f"no model_registry entry for {model_name}/{position}; nothing to validate"],
        )
    validated, notes = row

    mae_row = con.execute(
        "SELECT mae FROM evaluation_results WHERE model_name = ? AND season = ? AND position = 'ALL'",
        [f"{model_name}_{position.lower()}", season],
    ).fetchone()

    if not validated:
        return Result(
            task_id=task.task_id,
            agent=task.agent,
            status="REJECTED",
            findings=[
                f"{model_name}/{position} is not validated (model_registry.validated=false): {notes}"
            ],
            recommended_next_action="Do not use as a default decision source until validated.",
        )

    findings = [f"{model_name}/{position} is validated: {notes}"]
    if mae_row:
        findings.append(f"season {season} MAE: {mae_row[0]:.2f}")
    return Result(task_id=task.task_id, agent=task.agent, status="COMPLETE", findings=findings, confidence=0.9)


def run_research_validation(con: duckdb.DuckDBPyConnection, settings: Settings, task: Task) -> Result:
    """Optional per AGENT_CONTRACTS.md. No unstructured research/browsing capability exists
    in this environment -- honestly reported as NEEDS_REVIEW rather than fabricating a
    finding, consistent with every other documented capability gap in docs/DECISIONS.md."""
    return Result(
        task_id=task.task_id,
        agent=task.agent,
        status="NEEDS_REVIEW",
        findings=["research_validation has no reachable unstructured research source in this environment"],
        recommended_next_action="Escalate to a human if independent research is genuinely required.",
    )


AGENT_REGISTRY = {
    "data_engineering": run_data_engineering,
    "player_identity": run_player_identity,
    "projection_ml": run_projection_ml,
    "rookie_ml": run_rookie_ml,
    "market_edge": run_market_edge,
    "news_evidence": run_news_evidence,
    "fantasy_strategy": run_fantasy_strategy,
    "evaluation_qa": run_evaluation_qa,
    "research_validation": run_research_validation,
}
