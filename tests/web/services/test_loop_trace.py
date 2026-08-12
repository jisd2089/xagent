from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from xagent.web import models as _models  # noqa: F401
from xagent.web.models.database import Base
from xagent.web.models.task import Task, TraceEvent
from xagent.web.services.loop_trace import (
    LOOP_TRACE_EVENT_TYPE,
    create_loop_trace_task,
    emit_loop_trace_event,
    safe_loop_eval_trace_payload,
    summarize_loop_eval_summary,
)


def test_create_loop_trace_task_is_hidden_and_events_are_persisted() -> None:
    db = _session()

    task = create_loop_trace_task(
        db,
        user_id=1,
        title="Loop Eval Agent 31",
        description="trace anchor",
        agent_id=31,
    )
    event = emit_loop_trace_event(
        db,
        task_id=int(task.id),
        event_name="loop_eval_selected",
        step_id="loop_eval_selected",
        data={"case_count": 3},
    )

    persisted_task = db.query(Task).filter(Task.id == task.id).one()
    assert persisted_task.is_visible is False
    assert persisted_task.source == "internal"
    assert persisted_task.agent_id == 31
    assert event is not None
    persisted_event = db.query(TraceEvent).filter(TraceEvent.task_id == task.id).one()
    assert persisted_event.event_type == LOOP_TRACE_EVENT_TYPE
    assert persisted_event.step_id == "loop_eval_selected"
    assert persisted_event.data == {
        "type": "loop_eval_selected",
        "case_count": 3,
    }


def test_emit_loop_trace_event_allows_missing_anchor() -> None:
    db = _session()

    assert (
        emit_loop_trace_event(
            db,
            task_id=None,
            event_name="loop_eval_selected",
            data={"case_count": 3},
        )
        is None
    )
    assert db.query(TraceEvent).count() == 0


def test_safe_loop_eval_trace_payload_drops_credentials() -> None:
    payload = safe_loop_eval_trace_payload(
        {
            "dataset_manifest": "/data/dataset_manifest.json",
            "output_dir": "/data/out",
            "agent_id": 31,
            "dry_run": False,
            "api_base": "http://localhost",
            "worker_api_base": "http://nginx",
            "api_key": "secret",
            "login_username": "admin",
            "login_password": "admin123456",
            "api_key_secret_ref": "secret-ref",
            "reuse_task_map": {"case_a": 203},
            "budget": {"new_task_count": 0},
        }
    )

    assert payload["reuse_task_count"] == 1
    assert payload["budget"] == {"new_task_count": 0}
    assert "api_key" not in payload
    assert "login_username" not in payload
    assert "login_password" not in payload
    assert "api_key_secret_ref" not in payload


def test_summarize_loop_eval_summary_keeps_dashboard_fields() -> None:
    summary = summarize_loop_eval_summary(
        {
            "eval_dir": "/data/eval",
            "run_id": "dataset.agent31",
            "eval_run_id": "eval-run",
            "dataset_version": "dataset",
            "agent_id": 31,
            "api_base": "http://localhost",
            "worker_api_base": "http://nginx",
            "dry_run": False,
            "case_count": 2,
            "passed": 1,
            "failed": 1,
            "pass_rate": 0.5,
            "by_loop": {"loop1": {"total": 2}},
            "budget": {"new_task_count": 0},
            "raw_output": "not included",
        }
    )

    assert summary == {
        "eval_dir": "/data/eval",
        "run_id": "dataset.agent31",
        "eval_run_id": "eval-run",
        "dataset_version": "dataset",
        "agent_id": 31,
        "api_base": "http://localhost",
        "worker_api_base": "http://nginx",
        "dry_run": False,
        "case_count": 2,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
        "by_loop": {"loop1": {"total": 2}},
        "budget": {"new_task_count": 0},
        "stopped_early": None,
    }


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
