from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ...loop_data_factory.run_agent31_regression import run_regression
from ..models.background_job import BackgroundJob
from ..services.background_jobs import update_job_progress
from ..services.loop_eval_budget import (
    LoopEvalConcurrencyError,
    LoopEvalBudgetLease,
    acquire_loop_eval_budget_lease,
    record_loop_eval_budget_counters,
)
from ..services.loop_eval_reports import persist_loop_eval_report
from ..services.loop_trace import (
    emit_loop_trace_event,
    safe_loop_eval_trace_payload,
    summarize_loop_eval_summary,
)
from ..services.transient_secrets import delete_transient_secret, get_transient_secret


def handle_loop_eval_run(db: Session, job: BackgroundJob) -> dict[str, Any]:
    payload = dict(job.payload or {})
    requested_api_base = str(payload.get("api_base") or "http://localhost")
    worker_api_base = str(payload.get("worker_api_base") or requested_api_base)
    trace_task_id = _coerce_optional_int(payload.get("trace_task_id"))
    max_new_tasks = _coerce_int(payload.get("max_new_tasks", 3))
    budget = _coerce_budget(payload.get("budget"))
    new_task_count = int(budget.get("new_task_count") or 0)
    lock_scope = str(budget.get("scope") or f"agent-{int(payload.get('agent_id') or 31)}")
    lease: LoopEvalBudgetLease | None = None
    update_job_progress(
        db,
        job,
        message="Running loop eval",
        completed=0,
        total=1,
    )
    emit_loop_trace_event(
        db,
        task_id=trace_task_id,
        event_name="loop_eval_worker_started",
        step_id="loop_eval_worker",
        data={
            "job_id": str(job.id),
            **safe_loop_eval_trace_payload(payload),
        },
    )
    try:
        if new_task_count > 0:
            lease = acquire_loop_eval_budget_lease(
                job_id=str(job.id),
                new_task_count=new_task_count,
                ttl_seconds=int(float(payload.get("timeout_seconds") or 900.0)) + 600,
                scope=lock_scope,
            )
            record_loop_eval_budget_counters(
                db,
                user_id=int(job.user_id),
                scope=lock_scope,
                counters={
                    "jobs_started": 1,
                    "new_tasks_planned": new_task_count,
                },
                job_id=str(job.id),
                metadata={"mode": "background"},
            )
            update_job_progress(
                db,
                job,
                message="Loop eval concurrency lease acquired",
                completed=0,
                total=1,
                extra={"budget_scope": lock_scope, "new_task_count": new_task_count},
            )
            emit_loop_trace_event(
                db,
                task_id=trace_task_id,
                event_name="budget_lease_acquired",
                step_id="loop_eval_budget_guard",
                data={
                    "job_id": str(job.id),
                    "scope": lock_scope,
                    "new_task_count": new_task_count,
                    "ttl_seconds": int(float(payload.get("timeout_seconds") or 900.0)) + 600,
                },
            )
        summary = run_regression(
            dataset_manifest=Path(str(payload["dataset_manifest"])),
            agent_id=int(payload.get("agent_id") or 31),
            output_dir=Path(str(payload["output_dir"])),
            api_base=worker_api_base,
            api_key=_resolve_api_key(payload),
            login_username=payload.get("login_username"),
            login_password=payload.get("login_password"),
            rotate_runtime_key=bool(payload.get("rotate_runtime_key")),
            reuse_task_map=_coerce_reuse_task_map(payload.get("reuse_task_map")),
            dry_run=bool(payload.get("dry_run", True)),
            case_ids=_coerce_case_ids(payload.get("case_ids")),
            limit=_coerce_int(payload.get("limit")),
            max_new_tasks=max_new_tasks,
            stop_on_failure=bool(payload.get("stop_on_failure", False)),
            poll_interval=float(payload.get("poll_interval") or 2.0),
            timeout_seconds=float(payload.get("timeout_seconds") or 900.0),
            clean=bool(payload.get("clean", True)),
        )
    except Exception as exc:
        if isinstance(exc, LoopEvalConcurrencyError):
            record_loop_eval_budget_counters(
                db,
                user_id=int(job.user_id),
                scope=lock_scope,
                counters={"jobs_rejected_concurrency": 1},
                job_id=str(job.id),
                metadata={"mode": "background", "error_type": type(exc).__name__},
            )
        elif new_task_count > 0:
            record_loop_eval_budget_counters(
                db,
                user_id=int(job.user_id),
                scope=lock_scope,
                counters={"jobs_failed": 1},
                job_id=str(job.id),
                metadata={"mode": "background", "error_type": type(exc).__name__},
            )
        emit_loop_trace_event(
            db,
            task_id=trace_task_id,
            event_name="loop_eval_worker_failed",
            step_id="loop_eval_worker",
            data={
                "job_id": str(job.id),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        if lease is not None:
            lease.release(status="failed")
        raise
    finally:
        _delete_api_key_secret(payload)

    budget_summary = {
        **budget,
        "scope": lock_scope,
        "lock_acquired": bool(lease and lease.acquired),
        "max_new_tasks": max_new_tasks,
        "new_task_count": int(summary.get("new_task_count") or new_task_count),
        "stopped_early": bool(summary.get("stopped_early")),
    }
    summary["budget"] = budget_summary
    if worker_api_base != requested_api_base:
        summary["requested_api_base"] = requested_api_base
        summary["worker_api_base"] = worker_api_base
        summary["api_base"] = requested_api_base
    _write_summary_file(summary)
    eval_run = persist_loop_eval_report(
        db,
        user_id=int(job.user_id),
        background_job_id=str(job.id),
        eval_dir=Path(str(summary.get("eval_dir"))),
        summary=summary,
    )
    summary["eval_run_id"] = str(eval_run.id)
    _write_summary_file(summary)
    if lease is not None:
        lease.release(
            status="succeeded",
            completed_new_tasks=int(summary.get("new_task_count") or 0),
        )
        emit_loop_trace_event(
            db,
            task_id=trace_task_id,
            event_name="budget_lease_released",
            step_id="loop_eval_budget_guard",
            data={
                "job_id": str(job.id),
                "scope": lock_scope,
                "status": "succeeded",
                "completed_new_tasks": int(summary.get("new_task_count") or 0),
            },
        )
        record_loop_eval_budget_counters(
            db,
            user_id=int(job.user_id),
            scope=lock_scope,
            counters={
                "jobs_succeeded": 1,
                "new_tasks_completed": int(summary.get("new_task_count") or 0),
            },
            job_id=str(job.id),
            metadata={"mode": "background", "eval_dir": str(summary.get("eval_dir") or "")},
        )
    emit_loop_trace_event(
        db,
        task_id=trace_task_id,
        event_name="loop_eval_worker_completed",
        step_id="loop_eval_completed",
        data={
            "job_id": str(job.id),
            **summarize_loop_eval_summary(summary),
        },
    )
    update_job_progress(
        db,
        job,
        message="Loop eval completed",
        completed=1,
        total=1,
        extra={"eval_dir": summary.get("eval_dir")},
    )
    return summary


def _coerce_reuse_task_map(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("reuse_task_map must be an object")
    return {str(case_id): int(task_id) for case_id, task_id in value.items()}


def _coerce_case_ids(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("case_ids must be a list")
    return [str(item) for item in value]


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _coerce_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _coerce_budget(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _resolve_api_key(payload: dict[str, Any]) -> str | None:
    secret_ref = payload.get("api_key_secret_ref")
    if isinstance(secret_ref, str) and secret_ref:
        return get_transient_secret(secret_ref)
    api_key = payload.get("api_key")
    return str(api_key) if api_key else None


def _delete_api_key_secret(payload: dict[str, Any]) -> None:
    secret_ref = payload.get("api_key_secret_ref")
    if isinstance(secret_ref, str) and secret_ref:
        delete_transient_secret(secret_ref)


def _write_summary_file(summary: dict[str, Any]) -> None:
    eval_dir = summary.get("eval_dir")
    if not eval_dir:
        return
    summary_path = Path(str(eval_dir)) / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
