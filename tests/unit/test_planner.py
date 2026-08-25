"""Unit tests for D47's task planner: real dependency-graph construction from a high-level
goal, verified both structurally (edges are correct) and by actually running the generated
graph through the real orchestrator with stub agents (proving the edges are not just
plausible-looking but genuinely schedulable and correctly ordered/parallel)."""

from __future__ import annotations

import threading
import time

import pytest

from alpha_squad.agents import orchestrator as orchestrator_module
from alpha_squad.agents import registry as registry_module
from alpha_squad.agents.contracts import Result
from alpha_squad.agents.planner import plan_full_refresh
from alpha_squad.config.settings import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


class TestPlanFullRefreshStructure:
    def test_default_plan_includes_every_optional_stage(self):
        tasks = plan_full_refresh("run1", 2023, 2025)
        agents = {t.agent for t in tasks}
        assert agents == {
            "data_engineering",
            "player_identity",
            "projection_ml",
            "rookie_ml",
            "market_edge",
            "news_evidence",
            "evaluation_qa",
        }

    def test_include_flags_control_which_optional_stages_appear(self):
        tasks = plan_full_refresh(
            "run1",
            2023,
            2025,
            include_rookie=False,
            include_market_edge=False,
            include_evidence=False,
            include_qa=False,
        )
        agents = {t.agent for t in tasks}
        assert agents == {"data_engineering", "player_identity", "projection_ml"}

    def test_identity_is_the_only_task_with_no_dependencies(self):
        tasks = plan_full_refresh("run1", 2023, 2025)
        by_id = {t.task_id: t for t in tasks}
        roots = [t for t in tasks if not t.depends_on]
        assert len(roots) == 1
        assert roots[0].agent == "data_engineering"
        assert by_id["run1-identity"].depends_on == ["run1-data"]

    def test_market_edge_depends_on_projection_not_just_identity(self):
        # Real dependency: market/edge.py reads uncertainty_predictions, which only
        # projection_ml's run_uncertainty call writes -- market_edge must not be schedulable
        # before projection_ml has actually run.
        tasks = plan_full_refresh("run1", 2023, 2025)
        market_edge = next(t for t in tasks if t.agent == "market_edge")
        assert "run1-projection" in market_edge.depends_on

    def test_rookie_and_projection_share_only_identity_as_a_dependency(self):
        # Both only need identity, not each other -- this is what makes them genuinely
        # eligible to run concurrently once identity completes.
        tasks = plan_full_refresh("run1", 2023, 2025)
        projection = next(t for t in tasks if t.agent == "projection_ml")
        rookie = next(t for t in tasks if t.agent == "rookie_ml")
        assert projection.depends_on == ["run1-identity"]
        assert rookie.depends_on == ["run1-identity"]

    def test_qa_tasks_are_created_one_per_requested_position_depending_on_projection(self):
        tasks = plan_full_refresh("run1", 2023, 2025, qa_positions=("QB", "RB"))
        qa_tasks = [t for t in tasks if t.agent == "evaluation_qa"]
        assert len(qa_tasks) == 2
        assert all(t.depends_on == ["run1-projection"] for t in qa_tasks)
        assert {t.params["position"] for t in qa_tasks} == {"QB", "RB"}

    def test_fantasy_strategy_depends_on_every_included_upstream_stage(self):
        tasks = plan_full_refresh(
            "run1", 2023, 2025, fantasy_strategy={"decision_type": "draft_pick", "season": 2025}
        )
        strategy = next(t for t in tasks if t.agent == "fantasy_strategy")
        assert set(strategy.depends_on) == {"run1-projection", "run1-rookie", "run1-market-edge"}

    def test_fantasy_strategy_omitted_when_not_requested(self):
        tasks = plan_full_refresh("run1", 2023, 2025)
        assert not any(t.agent == "fantasy_strategy" for t in tasks)

    def test_no_task_depends_on_a_task_that_does_not_exist_in_the_plan(self):
        # Structural sanity: every depends_on id must resolve to a real task_id in the plan,
        # for every include_* combination -- a dangling dependency would silently never
        # become ready in the real orchestrator.
        for include_rookie in (True, False):
            for include_market_edge in (True, False):
                tasks = plan_full_refresh(
                    "run1",
                    2023,
                    2025,
                    include_rookie=include_rookie,
                    include_market_edge=include_market_edge,
                    include_evidence=False,
                    include_qa=False,
                    fantasy_strategy={"decision_type": "draft_pick", "season": 2025},
                )
                ids = {t.task_id for t in tasks}
                for t in tasks:
                    for dep in t.depends_on:
                        assert dep in ids, f"{t.task_id} depends on missing {dep}"


class TestPlanFullRefreshActuallyRuns:
    """Runs the generated plan through the real orchestrator (stub agents standing in for the
    real M1-M10 work, same pattern test_agents.py's orchestrator tests use) -- proving the
    dependency edges are genuinely schedulable, not just structurally plausible."""

    def test_generated_plan_runs_to_completion_in_the_real_orchestrator(
        self, settings, monkeypatch
    ):
        def make_stub(agent_name):
            def fn(con, s, task):
                return Result(task_id=task.task_id, agent=task.agent, status="COMPLETE")

            return fn

        for agent in (
            "data_engineering",
            "player_identity",
            "projection_ml",
            "rookie_ml",
            "market_edge",
            "news_evidence",
            "evaluation_qa",
        ):
            monkeypatch.setitem(registry_module.AGENT_REGISTRY, agent, make_stub(agent))

        tasks = plan_full_refresh("run1", 2023, 2025)
        report = orchestrator_module.run_pipeline(settings, "run1", tasks, max_workers=4)

        assert len(report.results) == len(tasks)
        assert all(r.status == "COMPLETE" for r in report.results.values())
        # Real ordering constraint: identity must finish before projection starts appearing
        # in the completion order (order here is completion order, not start order, but
        # projection can never complete before identity does given the real dependency wait).
        assert report.order.index("run1-identity") < report.order.index("run1-projection")
        assert report.order.index("run1-projection") < report.order.index("run1-market-edge")

    def test_rookie_and_projection_genuinely_run_concurrently_once_identity_completes(
        self, settings, monkeypatch
    ):
        start_times = {}
        lock = threading.Lock()

        def slow_stub(con, s, task):
            with lock:
                start_times[task.task_id] = time.monotonic()
            time.sleep(0.3)
            return Result(task_id=task.task_id, agent=task.agent, status="COMPLETE")

        def fast_stub(con, s, task):
            return Result(task_id=task.task_id, agent=task.agent, status="COMPLETE")

        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "data_engineering", fast_stub)
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "player_identity", fast_stub)
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "projection_ml", slow_stub)
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "rookie_ml", slow_stub)

        tasks = plan_full_refresh(
            "run1", 2023, 2025, include_market_edge=False, include_evidence=False, include_qa=False
        )
        orchestrator_module.run_pipeline(settings, "run1", tasks, max_workers=4)

        assert abs(start_times["run1-projection"] - start_times["run1-rookie"]) < 0.2

    def test_market_edge_never_starts_before_projection_completes(self, settings, monkeypatch):
        events: list[tuple[str, str]] = []
        lock = threading.Lock()

        def slow_projection(con, s, task):
            with lock:
                events.append((task.task_id, "start"))
            time.sleep(0.2)
            with lock:
                events.append((task.task_id, "end"))
            return Result(task_id=task.task_id, agent=task.agent, status="COMPLETE")

        def fast_stub(con, s, task):
            with lock:
                events.append((task.task_id, "start"))
                events.append((task.task_id, "end"))
            return Result(task_id=task.task_id, agent=task.agent, status="COMPLETE")

        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "data_engineering", fast_stub)
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "player_identity", fast_stub)
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "projection_ml", slow_projection)
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "market_edge", fast_stub)

        tasks = plan_full_refresh(
            "run1", 2023, 2025, include_rookie=False, include_evidence=False, include_qa=False
        )
        orchestrator_module.run_pipeline(settings, "run1", tasks, max_workers=4)

        projection_end = next(
            i for i, (tid, e) in enumerate(events) if tid == "run1-projection" and e == "end"
        )
        market_edge_start = next(
            i for i, (tid, e) in enumerate(events) if tid == "run1-market-edge" and e == "start"
        )
        assert market_edge_start > projection_end
