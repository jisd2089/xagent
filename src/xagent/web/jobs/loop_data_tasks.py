from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models.background_job import BackgroundJob
from ..services.background_jobs import update_job_progress
from ..services.loop_trace import emit_loop_trace_event
from ..api.loop_data import run_loop_data_generation_payload


def handle_loop_data_generate(db: Session, job: BackgroundJob) -> dict[str, Any]:
    payload = dict(job.payload or {})
    trace_task_id = _coerce_optional_int(payload.get("trace_task_id"))
    update_job_progress(
        db,
        job,
        message="Generating loop data",
        completed=0,
        total=1,
    )
    emit_loop_trace_event(
        db,
        task_id=trace_task_id,
        event_name="dataset_generation_worker_started",
        step_id="dataset_generation",
        data={
            "job_id": str(job.id),
            "level": payload.get("level"),
            "loops": payload.get("loops"),
            "output_dir": payload.get("output_dir"),
            "seed_dir": payload.get("seed_dir"),
            "adversarial_copies": payload.get("adversarial_copies_per_case"),
        },
    )
    try:
        result = run_loop_data_generation_payload(payload)
    except Exception as exc:
        emit_loop_trace_event(
            db,
            task_id=trace_task_id,
            event_name="dataset_generation_worker_failed",
            step_id="dataset_generation",
            data={
                "job_id": str(job.id),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        raise

    emit_loop_trace_event(
        db,
        task_id=trace_task_id,
        event_name="dataset_generation_worker_completed",
        step_id="dataset_generation",
        data={
            "job_id": str(job.id),
            **{
                key: result.get(key)
                for key in (
                    "dataset_version",
                    "level",
                    "loops",
                    "case_count",
                    "coverage_report",
                    "local_seed_summary",
                    "adversarial",
                    "mutation_plan",
                )
            },
        },
    )
    update_job_progress(
        db,
        job,
        message="Loop data generation completed",
        completed=1,
        total=1,
        extra={"manifest_path": result.get("manifest_path")},
    )
    return result


def _coerce_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
