"""Persistent orchestrator state -- agent_tasks/agent_results. `reconstruct_run` is the
literal answer to IMPLEMENTATION_PLAN.md's M11 gate: the orchestrator must be able to
reconstruct a full run purely from this state, with no chat transcript or in-memory data."""

from __future__ import annotations

import json

import duckdb

from alpha_squad.agents.contracts import Result, Task
from alpha_squad.sources.base import utcnow


def create_task(con: duckdb.DuckDBPyConnection, run_id: str, task: Task) -> None:
    con.execute(
        """
        INSERT INTO agent_tasks
            (task_id, run_id, agent, objective, priority, depends_on_json, params_json,
             status, attempt, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'PLANNED', 0, ?)
        ON CONFLICT (task_id) DO NOTHING
        """,
        [
            task.task_id,
            run_id,
            task.agent,
            task.objective,
            task.priority,
            json.dumps(task.depends_on),
            json.dumps(task.params),
            utcnow(),
        ],
    )


def set_task_status(
    con: duckdb.DuckDBPyConnection, task_id: str, status: str, *, increment_attempt: bool = False
) -> None:
    now = utcnow()
    if status == "RUNNING":
        if increment_attempt:
            con.execute(
                "UPDATE agent_tasks SET status = ?, started_at = ?, attempt = attempt + 1 WHERE task_id = ?",
                [status, now, task_id],
            )
        else:
            con.execute(
                "UPDATE agent_tasks SET status = ?, started_at = ? WHERE task_id = ?",
                [status, now, task_id],
            )
    elif status in ("COMPLETE", "FAILED", "REJECTED"):
        con.execute(
            "UPDATE agent_tasks SET status = ?, finished_at = ? WHERE task_id = ?",
            [status, now, task_id],
        )
    else:
        con.execute("UPDATE agent_tasks SET status = ? WHERE task_id = ?", [status, task_id])


def record_result(con: duckdb.DuckDBPyConnection, result: Result) -> None:
    con.execute(
        """
        INSERT INTO agent_results
            (task_id, agent, status, confidence, findings_json, artifacts_json, tests_json,
             risks_json, open_questions_json, recommended_next_action, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (task_id) DO UPDATE SET
            status = excluded.status, confidence = excluded.confidence,
            findings_json = excluded.findings_json, artifacts_json = excluded.artifacts_json,
            tests_json = excluded.tests_json, risks_json = excluded.risks_json,
            open_questions_json = excluded.open_questions_json,
            recommended_next_action = excluded.recommended_next_action,
            recorded_at = excluded.recorded_at
        """,
        [
            result.task_id,
            result.agent,
            result.status,
            result.confidence,
            json.dumps(result.findings),
            json.dumps(result.artifacts),
            json.dumps([t.model_dump() for t in result.tests]),
            json.dumps(result.risks),
            json.dumps(result.open_questions),
            result.recommended_next_action,
            utcnow(),
        ],
    )


def task_status(con: duckdb.DuckDBPyConnection, task_id: str) -> str | None:
    row = con.execute("SELECT status FROM agent_tasks WHERE task_id = ?", [task_id]).fetchone()
    return row[0] if row else None


def record_milestone(
    con: duckdb.DuckDBPyConnection,
    milestone: str,
    run_id: str,
    status: str,
    notes: str | None = None,
) -> None:
    """ACCEPTANCE_CRITERIA.md: "Milestone state is persistent." Called by the orchestrator
    at the start and end of a run so a milestone's status survives independently of any
    individual task's state."""
    now = utcnow()
    existing = con.execute(
        "SELECT started_at FROM milestones WHERE milestone = ? AND run_id = ?", [milestone, run_id]
    ).fetchone()
    started_at = existing[0] if existing else now
    completed_at = now if status in ("COMPLETE", "FAILED") else None
    con.execute(
        """
        INSERT INTO milestones (milestone, run_id, status, started_at, completed_at, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (milestone, run_id) DO UPDATE SET
            status = excluded.status, completed_at = excluded.completed_at, notes = excluded.notes
        """,
        [milestone, run_id, status, started_at, completed_at, notes],
    )


def reconstruct_run(con: duckdb.DuckDBPyConnection, run_id: str) -> dict:
    """Rebuilds a run's full status purely from agent_tasks/agent_results DB state."""
    tasks = con.execute(
        "SELECT task_id, agent, objective, priority, depends_on_json, status, attempt, "
        "created_at, started_at, finished_at FROM agent_tasks WHERE run_id = ? ORDER BY created_at",
        [run_id],
    ).fetchall()
    task_ids = [t[0] for t in tasks]
    results = {}
    if task_ids:
        for row in con.execute(
            "SELECT task_id, status, confidence, findings_json, tests_json, recommended_next_action "
            "FROM agent_results WHERE task_id = ANY(?)",
            [task_ids],
        ).fetchall():
            results[row[0]] = row

    task_summaries = []
    for t in tasks:
        task_id = t[0]
        r = results.get(task_id)
        task_summaries.append(
            {
                "task_id": task_id,
                "agent": t[1],
                "objective": t[2],
                "priority": t[3],
                "depends_on": json.loads(t[4]),
                "status": t[5],
                "attempt": t[6],
                "created_at": str(t[7]),
                "started_at": str(t[8]) if t[8] else None,
                "finished_at": str(t[9]) if t[9] else None,
                "result": (
                    {
                        "status": r[1],
                        "confidence": r[2],
                        "findings": json.loads(r[3]),
                        "tests": json.loads(r[4]),
                        "recommended_next_action": r[5],
                    }
                    if r
                    else None
                ),
            }
        )
    return {"run_id": run_id, "tasks": task_summaries}
