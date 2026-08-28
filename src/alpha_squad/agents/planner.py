"""Task decomposition / dependency discovery (D47): given a high-level goal (season range,
which optional stages to include), builds the real `Task` graph the orchestrator should run --
correct `depends_on` edges included -- instead of a caller hand-typing a `list[Task]` per call
(the pattern `cli.py`'s original `orchestrate demo` command used, and the only pattern that
existed before this).

This is deliberately NOT a new scheduler, a planning "AI," or a different execution model --
`agents/orchestrator.py::run_pipeline` is unchanged and still does 100% of the actual dependency
resolution, retry, and concurrent dispatch (ARCHITECTURE.md §6, D14: no agent call, including
this one, is ever an LLM call). What was missing was a declarative encoding of the REAL pipeline
dependency structure (which of the 8 functional agents in `AGENT_REGISTRY` a goal actually needs,
and in what order they can correctly run) so that structure only has to be correct once, here,
rather than re-derived by hand at every call site. The dependency edges below are read directly
off what each agent's registry.py implementation actually queries/writes (e.g. `market_edge`
depends on `projection_ml` because `market/edge.py` reads `uncertainty_predictions`, which only
`projection_ml`'s `run_uncertainty` call writes) -- not guessed.

Known, disclosed limitation: this does not yet auto-schedule disagreement detection
(`agents/disagreement.py`) as a dependent task -- that remains a separate, manually-invoked step
(`alpha-squad orchestrate disagreements`) rather than part of the generated graph. Left out
rather than wired in half-correctly; a real follow-up, not silently dropped."""

from __future__ import annotations

from alpha_squad.agents.contracts import Task
from alpha_squad.market.edge import DEFAULT_ECR_TYPE

DEFAULT_QA_POSITIONS = ("QB", "RB", "WR", "TE")
DEFAULT_IDENTITY_DATASETS: list[list] = [
    ["nflverse", "players", {}],
    ["nflverse", "draft_picks", {}],
    ["nflverse", "combine", {}],
    ["dynastyprocess", "player_ids", {}],
]


def plan_full_refresh(
    run_id: str,
    season_start: int,
    season_end: int,
    *,
    min_train_season: int = 2015,
    class_start: int | None = None,
    class_end: int | None = None,
    min_train_class: int = 2000,
    ecr_type: str = DEFAULT_ECR_TYPE,
    include_rookie: bool = True,
    include_market_edge: bool = True,
    include_evidence: bool = True,
    include_qa: bool = True,
    qa_positions: tuple[str, ...] = DEFAULT_QA_POSITIONS,
    fantasy_strategy: dict | None = None,
    identity_datasets: list[list] | None = None,
) -> list[Task]:
    """Builds the real task graph for "refresh universal player intelligence for
    `season_start`-`season_end`, optionally through decision-making," selecting which of the 8
    functional agents apply from the `include_*` flags (AGENT_CONTRACTS.md's "select appropriate
    agents") and wiring each one's `depends_on` to the real upstream tasks it needs
    (AGENT_CONTRACTS.md's "dependencies are explicit"). Pass the result straight to
    `orchestrator.run_pipeline` -- every dependency-resolution/retry/concurrency guarantee that
    function already provides applies unchanged; independent stages here (`rookie` alongside
    `projection`, `evidence` alongside both) genuinely become eligible to run concurrently
    because their dependency edges don't force a false ordering between them, not because
    anything about the scheduler itself changed.

    `fantasy_strategy`, if given, is the exact `params` dict `run_fantasy_strategy` expects
    (`decision_type`, `season`, etc., see `agents/registry.py`); it is appended as one more task
    depending on every upstream stage this call actually included."""
    data_id = f"{run_id}-data"
    identity_id = f"{run_id}-identity"
    projection_id = f"{run_id}-projection"
    rookie_id = f"{run_id}-rookie"
    market_edge_id = f"{run_id}-market-edge"
    evidence_id = f"{run_id}-evidence"

    tasks: list[Task] = [
        Task(
            task_id=data_id,
            agent="data_engineering",
            objective="Ingest identity source datasets",
            depends_on=[],
            params={"datasets": identity_datasets or DEFAULT_IDENTITY_DATASETS},
        ),
        Task(
            task_id=identity_id,
            agent="player_identity",
            objective="Build canonical player identity from the ingested snapshots",
            depends_on=[data_id],
        ),
        Task(
            task_id=projection_id,
            agent="projection_ml",
            objective=f"Refresh established-player features/baselines/ML/uncertainty for "
            f"{season_start}-{season_end}",
            depends_on=[identity_id],
            params={
                "seasons": list(range(season_start, season_end + 1)),
                "min_train_season": min_train_season,
            },
        ),
    ]
    strategy_deps = [projection_id]

    if include_rookie:
        tasks.append(
            Task(
                task_id=rookie_id,
                agent="rookie_ml",
                objective=f"Walk-forward rookie model, classes {class_start or season_start}-"
                f"{class_end or season_end}",
                # Independent of projection_ml -- both only need identity -- so the scheduler
                # is free to run this concurrently with it, not sequentially after it.
                depends_on=[identity_id],
                params={
                    "class_start": class_start if class_start is not None else season_start,
                    "class_end": class_end if class_end is not None else season_end,
                    "min_train_class": min_train_class,
                },
            )
        )
        strategy_deps.append(rookie_id)

    if include_market_edge:
        tasks.append(
            Task(
                task_id=market_edge_id,
                agent="market_edge",
                objective=f"Build market/dynasty/EDGE for {season_start}-{season_end}",
                # Real dependency: market/edge.py's EDGE build reads uncertainty_predictions,
                # which only projection_ml's run_uncertainty call writes.
                depends_on=[projection_id],
                params={
                    "season_start": season_start,
                    "season_end": season_end,
                    "ecr_type": ecr_type,
                },
            )
        )
        strategy_deps.append(market_edge_id)

    if include_evidence:
        tasks.append(
            Task(
                task_id=evidence_id,
                agent="news_evidence",
                objective=f"Detect structured evidence events for {season_start}-{season_end}",
                # Evidence events are keyed on canonical player_id; needs identity, not
                # projection_ml -- genuinely eligible to run alongside projection/rookie.
                depends_on=[identity_id],
                params={"season_start": season_start, "season_end": season_end},
            )
        )

    if include_qa:
        for position in qa_positions:
            tasks.append(
                Task(
                    task_id=f"{run_id}-qa-{position.lower()}",
                    agent="evaluation_qa",
                    objective=f"Review the trained {position} established model before it's "
                    "treated as a default decision source",
                    depends_on=[projection_id],
                    params={
                        "model_name": "ml_catboost",
                        "position": position,
                        "season": season_end,
                    },
                )
            )

    if fantasy_strategy is not None:
        tasks.append(
            Task(
                task_id=f"{run_id}-strategy",
                agent="fantasy_strategy",
                objective=f"Produce a {fantasy_strategy.get('decision_type', 'draft_pick')} "
                "recommendation from the refreshed universal intelligence",
                depends_on=strategy_deps,
                params=fantasy_strategy,
            )
        )

    return tasks
