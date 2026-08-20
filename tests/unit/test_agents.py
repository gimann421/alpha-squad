"""Unit tests for the agent contracts, persistent state, DAG orchestrator, and disagreement
protocol -- all against synthetic data. The orchestrator tests use stub agents (registered
via monkeypatch) so they exercise real scheduling/retry/concurrency logic without re-testing
M1-M10's already-tested internals."""

from __future__ import annotations

import threading
import time

import duckdb
import pytest

from alpha_squad.agents import orchestrator as orchestrator_module
from alpha_squad.agents import registry as registry_module
from alpha_squad.agents.contracts import Result, Task
from alpha_squad.agents.disagreement import (
    detect_baseline_vs_ml_disagreements,
    detect_model_vs_market_disagreements,
    resolve_and_record,
)
from alpha_squad.agents.state import (
    create_task,
    reconstruct_run,
    record_milestone,
    record_result,
    set_task_status,
)
from alpha_squad.config.settings import Settings
from alpha_squad.storage.db import init_db


class TestContracts:
    def test_task_defaults_are_empty_not_none(self):
        task = Task(task_id="T1", agent="projection_ml", objective="test")
        assert task.depends_on == []
        assert task.priority == "MEDIUM"

    def test_task_allows_extra_fields(self):
        task = Task(task_id="T1", agent="x", objective="y", extra_field=123)
        assert task.model_dump()["extra_field"] == 123

    def test_result_status_and_tests_round_trip(self):
        result = Result(
            task_id="T1",
            agent="projection_ml",
            status="COMPLETE",
            confidence=0.87,
            tests=[{"name": "no_future_leakage", "status": "PASS"}],
        )
        assert result.tests[0].name == "no_future_leakage"
        assert result.tests[0].status == "PASS"


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


class TestAgentState:
    def test_create_task_is_idempotent(self, con):
        task = Task(task_id="T1", agent="projection_ml", objective="x")
        create_task(con, "run1", task)
        create_task(con, "run1", task)
        n = con.execute("SELECT count(*) FROM agent_tasks WHERE task_id='T1'").fetchone()[0]
        assert n == 1

    def test_set_task_status_running_increments_attempt_and_sets_started_at(self, con):
        create_task(con, "run1", Task(task_id="T1", agent="a", objective="x"))
        set_task_status(con, "T1", "RUNNING", increment_attempt=True)
        row = con.execute(
            "SELECT status, attempt, started_at FROM agent_tasks WHERE task_id='T1'"
        ).fetchone()
        assert row[0] == "RUNNING"
        assert row[1] == 1
        assert row[2] is not None

    def test_set_task_status_complete_sets_finished_at(self, con):
        create_task(con, "run1", Task(task_id="T1", agent="a", objective="x"))
        set_task_status(con, "T1", "COMPLETE")
        row = con.execute("SELECT finished_at FROM agent_tasks WHERE task_id='T1'").fetchone()
        assert row[0] is not None

    def test_record_result_upserts(self, con):
        create_task(con, "run1", Task(task_id="T1", agent="a", objective="x"))
        record_result(con, Result(task_id="T1", agent="a", status="COMPLETE", confidence=0.5))
        record_result(con, Result(task_id="T1", agent="a", status="FAILED", confidence=0.1))
        row = con.execute(
            "SELECT status, confidence FROM agent_results WHERE task_id='T1'"
        ).fetchone()
        assert row == ("FAILED", 0.1)

    def test_reconstruct_run_rebuilds_full_state_with_no_external_context(self, con):
        """The M11 gate: the orchestrator must be able to reconstruct a full run purely from
        DB state."""
        create_task(con, "run1", Task(task_id="T1", agent="a", objective="do x", depends_on=["T0"]))
        set_task_status(con, "T1", "RUNNING", increment_attempt=True)
        record_result(
            con, Result(task_id="T1", agent="a", status="COMPLETE", confidence=0.9, findings=["ok"])
        )
        set_task_status(con, "T1", "COMPLETE")

        rebuilt = reconstruct_run(con, "run1")
        assert rebuilt["run_id"] == "run1"
        assert len(rebuilt["tasks"]) == 1
        t = rebuilt["tasks"][0]
        assert t["task_id"] == "T1"
        assert t["depends_on"] == ["T0"]
        assert t["status"] == "COMPLETE"
        assert t["attempt"] == 1
        assert t["result"]["status"] == "COMPLETE"
        assert t["result"]["findings"] == ["ok"]

    def test_reconstruct_run_scopes_to_the_given_run_id(self, con):
        create_task(con, "run1", Task(task_id="T1", agent="a", objective="x"))
        create_task(con, "run2", Task(task_id="T2", agent="a", objective="y"))
        rebuilt = reconstruct_run(con, "run1")
        assert [t["task_id"] for t in rebuilt["tasks"]] == ["T1"]

    def test_record_milestone_persists_across_status_updates(self, con):
        record_milestone(con, "m1", "run1", "RUNNING")
        row = con.execute(
            "SELECT status, started_at, completed_at FROM milestones WHERE milestone='m1' AND run_id='run1'"
        ).fetchone()
        assert row[0] == "RUNNING"
        assert row[1] is not None
        assert row[2] is None

        record_milestone(con, "m1", "run1", "COMPLETE", notes="done")
        row = con.execute(
            "SELECT status, completed_at, notes FROM milestones WHERE milestone='m1' AND run_id='run1'"
        ).fetchone()
        assert row[0] == "COMPLETE"
        assert row[1] is not None
        assert row[2] == "done"


def _stub_ok(name):
    def fn(con, settings, task):
        return Result(
            task_id=task.task_id, agent=task.agent, status="COMPLETE", findings=[f"{name} ran"]
        )

    return fn


def _stub_fail(con, settings, task):
    raise RuntimeError("boom")


def _stub_fail_then_ok():
    calls = {"n": 0}

    def fn(con, settings, task):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return Result(
            task_id=task.task_id, agent=task.agent, status="COMPLETE", findings=["recovered"]
        )

    return fn


def _connect(settings: Settings):
    from alpha_squad.storage.db import get_connection, init_db

    con = get_connection(settings)
    init_db(con)
    return con


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path / "data", db_path=tmp_path / "data" / "x.duckdb")


class TestOrchestrator:
    def test_runs_tasks_in_dependency_order(self, settings, monkeypatch):
        order_lock = threading.Lock()
        order = []

        def make_stub(name):
            def fn(con, s, task):
                with order_lock:
                    order.append(task.task_id)
                return Result(task_id=task.task_id, agent=task.agent, status="COMPLETE")

            return fn

        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "agent_a", make_stub("a"))
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "agent_b", make_stub("b"))

        tasks = [
            Task(task_id="T1", agent="agent_a", objective="first"),
            Task(task_id="T2", agent="agent_b", objective="second", depends_on=["T1"]),
        ]
        report = orchestrator_module.run_pipeline(settings, "run1", tasks, max_workers=2)
        assert order == ["T1", "T2"]
        assert report.results["T1"].status == "COMPLETE"
        assert report.results["T2"].status == "COMPLETE"

    def test_independent_tasks_run_concurrently(self, settings, monkeypatch):
        start_times = {}
        start_lock = threading.Lock()

        def slow_stub(con, s, task):
            with start_lock:
                start_times[task.task_id] = time.monotonic()
            time.sleep(0.3)
            return Result(task_id=task.task_id, agent=task.agent, status="COMPLETE")

        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "slow_agent", slow_stub)
        tasks = [
            Task(task_id="T1", agent="slow_agent", objective="x"),
            Task(task_id="T2", agent="slow_agent", objective="y"),
        ]
        orchestrator_module.run_pipeline(settings, "run1", tasks, max_workers=2)
        # Two independent 0.3s tasks starting within 0.2s of each other proves real
        # concurrent dispatch, not accidental sequential execution.
        assert abs(start_times["T1"] - start_times["T2"]) < 0.2

    def test_run_pipeline_persists_milestone_state(self, settings, monkeypatch):
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "agent_a", _stub_ok("a"))
        tasks = [Task(task_id="T1", agent="agent_a", objective="x")]
        orchestrator_module.run_pipeline(settings, "run1", tasks)

        con = _connect(settings)
        try:
            row = con.execute(
                "SELECT status FROM milestones WHERE milestone='orchestrated_run' AND run_id='run1'"
            ).fetchone()
            assert row[0] == "COMPLETE"
        finally:
            con.close()

    def test_failed_dependency_blocks_downstream_task(self, settings, monkeypatch):
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "failing_agent", _stub_fail)
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "ok_agent", _stub_ok("ok"))
        tasks = [
            Task(task_id="T1", agent="failing_agent", objective="x"),
            Task(task_id="T2", agent="ok_agent", objective="y", depends_on=["T1"]),
        ]
        report = orchestrator_module.run_pipeline(settings, "run1", tasks, max_workers=2)
        assert report.results["T1"].status == "FAILED"
        assert "T2" not in report.results  # never ran

        con = _connect(settings)
        try:
            status = con.execute("SELECT status FROM agent_tasks WHERE task_id='T2'").fetchone()[0]
            assert status == "BLOCKED"
        finally:
            con.close()

    def test_retries_transient_failures_before_giving_up(self, settings, monkeypatch):
        monkeypatch.setitem(registry_module.AGENT_REGISTRY, "flaky_agent", _stub_fail_then_ok())
        tasks = [Task(task_id="T1", agent="flaky_agent", objective="x")]
        report = orchestrator_module.run_pipeline(settings, "run1", tasks, max_workers=1)
        assert report.results["T1"].status == "COMPLETE"
        assert report.results["T1"].findings == ["recovered"]

    def test_unregistered_agent_fails_cleanly(self, settings):
        tasks = [Task(task_id="T1", agent="not_a_real_agent", objective="x")]
        report = orchestrator_module.run_pipeline(settings, "run1", tasks)
        assert report.results["T1"].status == "FAILED"


class TestDisagreementProtocol:
    def test_model_vs_market_disagreement_detected_from_real_edge_snapshot_shape(self, con):
        con.execute(
            """
            INSERT INTO edge_snapshot
                (edge_id, player_id, season, position, ecr_type, model_version, model_rank,
                 market_rank, rank_edge, evidence_score, confidence, action, reasons_json, built_at)
            VALUES ('e1', 'p1', 2025, 'WR', 'rsf', 'edge_v1', 5, 50, 45, 0.5, 0.8, 'BUY', '[]', current_timestamp)
            """
        )
        disagreements = detect_model_vs_market_disagreements(con, 2025, ecr_type="rsf")
        assert len(disagreements) == 1
        d = disagreements[0]
        assert d["subject"] == "p1"
        assert d["majority_position"] == "model"  # confidence 0.8 >= 0.5
        assert d["minority_position"] == "market"

    def test_small_rank_edge_is_not_a_disagreement(self, con):
        con.execute(
            """
            INSERT INTO edge_snapshot
                (edge_id, player_id, season, position, ecr_type, model_version, model_rank,
                 market_rank, rank_edge, evidence_score, confidence, action, reasons_json, built_at)
            VALUES ('e1', 'p1', 2025, 'WR', 'rsf', 'edge_v1', 5, 10, 5, 0.5, 0.8, 'WATCH', '[]', current_timestamp)
            """
        )
        assert detect_model_vs_market_disagreements(con, 2025) == []

    def test_baseline_vs_ml_disagreement_from_real_evaluation_results_shape(self, con):
        con.execute(
            "INSERT INTO evaluation_results (model_name, season, position, n, mae, evaluated_at) "
            "VALUES ('baseline_ecr_implied', 2025, 'WR', 50, 30.0, current_timestamp)"
        )
        con.execute(
            "INSERT INTO evaluation_results (model_name, season, position, n, mae, evaluated_at) "
            "VALUES ('ml_ensemble_wr', 2025, 'WR', 50, 15.0, current_timestamp)"
        )
        disagreements = detect_baseline_vs_ml_disagreements(con, 2025, "WR")
        assert len(disagreements) == 1
        assert disagreements[0]["majority_position"] == "ml_ensemble"
        assert disagreements[0]["minority_position"] == "baseline_ecr_implied"

    def test_resolve_and_record_preserves_both_positions(self, con):
        disagreement = {
            "disagreement_type": "market",
            "subject": "p1",
            "season": 2025,
            "majority_position": "model",
            "majority_value": 5.0,
            "minority_position": "market",
            "minority_value": 50.0,
            "critique": "test critique",
        }
        disagreement_id = resolve_and_record(con, "run1", disagreement)
        row = con.execute(
            "SELECT majority_position, majority_value, minority_position, minority_value, resolution "
            "FROM agent_disagreements WHERE disagreement_id = ?",
            [disagreement_id],
        ).fetchone()
        assert row[0] == "model" and row[1] == 5.0
        assert row[2] == "market" and row[3] == 50.0  # minority preserved, not discarded
        assert "model" in row[4]
