from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models.task import Task, TraceEvent

LOOP_TRACE_EVENT_TYPE = "loop_trace_event"


def create_loop_trace_task(
    db: Session,
    *,
    user_id: int,
    title: str,
    description: str | None = None,
    agent_id: int | None = None,
) -> Task:
    """Create a hidden task that anchors loop data/eval trace events."""
    task = Task(
        user_id=user_id,
        title=title[:200],
        description=description,
        agent_id=agent_id,
        source="internal",
        is_visible=False,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def emit_loop_trace_event(
    db: Session,
    *,
    task_id: int | None,
    event_name: str,
    data: dict[str, Any] | None = None,
    step_id: str | None = None,
) -> TraceEvent | None:
    if task_id is None:
        return None
    event_data = _jsonable_dict(
        {
            "type": event_name,
            **(data or {}),
        }
    )
    event = TraceEvent(
        task_id=task_id,
        event_id=str(uuid.uuid4()),
        event_type=LOOP_TRACE_EVENT_TYPE,
        timestamp=datetime.now(timezone.utc),
        step_id=step_id,
        parent_event_id=None,
        data=event_data,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def safe_loop_eval_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    budget = payload.get("budget")
    sampling = payload.get("sampling")
    reuse_task_map = payload.get("reuse_task_map")
    return {
        "dataset_manifest": payload.get("dataset_manifest"),
        "output_dir": payload.get("output_dir"),
        "agent_id": payload.get("agent_id"),
        "dry_run": payload.get("dry_run"),
        "api_base": payload.get("api_base"),
        "worker_api_base": payload.get("worker_api_base"),
        "case_ids": payload.get("case_ids"),
        "sampling": dict(sampling) if isinstance(sampling, dict) else sampling,
        "limit": payload.get("limit"),
        "budget": dict(budget) if isinstance(budget, dict) else budget,
        "reuse_task_count": len(reuse_task_map) if isinstance(reuse_task_map, dict) else 0,
    }


def summarize_loop_eval_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "eval_dir": summary.get("eval_dir"),
        "run_id": summary.get("run_id"),
        "eval_run_id": summary.get("eval_run_id"),
        "dataset_version": summary.get("dataset_version"),
        "agent_id": summary.get("agent_id"),
        "api_base": summary.get("api_base"),
        "worker_api_base": summary.get("worker_api_base"),
        "dry_run": summary.get("dry_run"),
        "case_count": summary.get("case_count"),
        "passed": summary.get("passed"),
        "failed": summary.get("failed"),
        "pass_rate": summary.get("pass_rate"),
        "by_loop": summary.get("by_loop"),
        "budget": summary.get("budget"),
        "stopped_early": summary.get("stopped_early"),
    }


def summarize_dataset_manifest(manifest: dict[str, Any], *, coverage_report: str) -> dict[str, Any]:
    summary = {
        "dataset_version": manifest.get("dataset_version"),
        "level": manifest.get("level"),
        "loops": manifest.get("loops"),
        "case_count": manifest.get("case_count"),
        "coverage_report": coverage_report,
    }
    for key in ("local_seed_summary", "adversarial", "mutation_plan"):
        if key in manifest:
            summary[key] = manifest.get(key)
    return summary


def _jsonable_dict(value: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except (TypeError, ValueError):
        return {
            "type": str(value.get("type") or "loop_trace_event"),
            "serialization_error": True,
        }
