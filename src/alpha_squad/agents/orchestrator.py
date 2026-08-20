"""DAG orchestrator: dependency resolution, retry/backoff, and concurrency-safe parallel
dispatch (ARCHITECTURE.md's engineering-layer orchestrator, D14 -- no agent call here is an
LLM). DuckDB's single embedded file does not support safe unserialized concurrent writes
from multiple connections/threads, so real parallelism happens at the scheduling/readiness
layer -- multiple independent tasks genuinely become READY and start running concurrently in
their own threads/connections -- while each task's actual DB reads/writes are serialized
through a shared lock. That is genuine concurrent scheduling with safe concurrent storage,
not a fake "parallel" that is secretly sequential."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from alpha_squad.agents.contracts import Result, Task
from alpha_squad.agents.registry import AGENT_REGISTRY
from alpha_squad.agents.state import create_task, record_milestone, record_result, set_task_status
from alpha_squad.config.settings import Settings

MAX_RETRIES = 2
BACKOFF_SECONDS = (1.0, 3.0)

_db_lock = threading.Lock()


@dataclass
class RunReport:
    run_id: str
    results: dict[str, Result] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)


def _ready_batch(
    tasks: dict[str, Task], statuses: dict[str, str], remaining: set[str]
) -> list[str]:
    ready = []
    for task_id in list(remaining):
        if statuses[task_id] not in ("PLANNED", "BLOCKED"):
            continue
        task = tasks[task_id]
        dep_statuses = [statuses[d] for d in task.depends_on if d in statuses]
        if len(dep_statuses) != len(task.depends_on):
            continue  # a declared dependency isn't part of this run at all
        if any(s in ("FAILED", "REJECTED") for s in dep_statuses):
            statuses[task_id] = "BLOCKED"
            continue
        if all(s == "COMPLETE" for s in dep_statuses):
            ready.append(task_id)
    return ready


def _run_one(con_factory, settings: Settings, task: Task) -> Result:
    agent_fn = AGENT_REGISTRY.get(task.agent)
    if agent_fn is None:
        result = Result(
            task_id=task.task_id,
            agent=task.agent,
            status="FAILED",
            findings=[f"no registered agent implementation for {task.agent!r}"],
        )
        con = con_factory()
        try:
            with _db_lock:
                record_result(con, result)
                set_task_status(con, task.task_id, "FAILED")
                con.commit()
        finally:
            con.close()
        return result

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        con = con_factory()
        try:
            with _db_lock:
                set_task_status(con, task.task_id, "RUNNING", increment_attempt=True)
                con.commit()
            result = agent_fn(con, settings, task)
            with _db_lock:
                record_result(con, result)
                set_task_status(con, task.task_id, result.status)
                con.commit()
            return result
        except Exception as e:  # noqa: BLE001 - a single agent's crash must not kill the run
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
        finally:
            con.close()

    result = Result(
        task_id=task.task_id,
        agent=task.agent,
        status="FAILED",
        findings=[f"crashed after {MAX_RETRIES + 1} attempts: {last_error!r}"],
    )
    con = con_factory()
    try:
        with _db_lock:
            record_result(con, result)
            set_task_status(con, task.task_id, "FAILED")
            con.commit()
    finally:
        con.close()
    return result


def run_pipeline(
    settings: Settings, run_id: str, tasks: list[Task], max_workers: int = 4
) -> RunReport:
    from alpha_squad.storage.db import get_connection, init_db

    # init_db (CREATE TABLE/ALTER TABLE DDL) must run exactly once, before any worker
    # threads open their own connections: DuckDB's catalog does not support concurrent DDL
    # against the same file from multiple connections (verified -- concurrent per-task
    # init_db calls raised a real "Catalog write-write conflict on alter" TransactionException
    # during review). Per-task connections below assume the schema already exists.
    def con_factory():
        return get_connection(settings)

    setup_con = con_factory()
    try:
        init_db(setup_con)
        for task in tasks:
            create_task(setup_con, run_id, task)
        record_milestone(setup_con, "orchestrated_run", run_id, "RUNNING")
        setup_con.commit()
    finally:
        setup_con.close()

    tasks_by_id = {t.task_id: t for t in tasks}
    statuses = {t.task_id: "PLANNED" for t in tasks}
    report = RunReport(run_id=run_id)
    remaining = set(tasks_by_id)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while remaining:
            ready = _ready_batch(tasks_by_id, statuses, remaining)
            if not ready:
                # Nothing is runnable: every remaining task is blocked on a failed/rejected
                # dependency (or a cycle/missing dependency, which never becomes ready).
                for task_id in remaining:
                    statuses.setdefault(task_id, "BLOCKED")
                    if statuses[task_id] not in ("COMPLETE", "FAILED", "REJECTED"):
                        con = con_factory()
                        try:
                            with _db_lock:
                                set_task_status(con, task_id, "BLOCKED")
                                con.commit()
                        finally:
                            con.close()
                break

            futures = {
                pool.submit(_run_one, con_factory, settings, tasks_by_id[task_id]): task_id
                for task_id in ready
            }
            for future in as_completed(futures):
                task_id = futures[future]
                result = future.result()
                statuses[task_id] = result.status
                report.results[task_id] = result
                report.order.append(task_id)
                remaining.discard(task_id)

    final_con = con_factory()
    try:
        overall_status = (
            "FAILED" if any(s in ("FAILED", "REJECTED") for s in statuses.values()) else "COMPLETE"
        )
        with _db_lock:
            record_milestone(
                final_con,
                "orchestrated_run",
                run_id,
                overall_status,
                notes=f"{len(report.results)}/{len(tasks)} tasks finished",
            )
            final_con.commit()
    finally:
        final_con.close()

    return report
