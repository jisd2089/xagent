from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..models.loop_eval import (
    SelectionEvalResult,
    SelectionEvalRun,
    SelectionLoopCase,
    SelectionLoopProfile,
    SelectionOutcome,
)


def persist_loop_eval_report(
    db: Session,
    *,
    user_id: int,
    eval_dir: Path,
    summary: dict[str, Any],
    background_job_id: str | None = None,
) -> SelectionEvalRun:
    report_path = str(eval_dir.resolve())
    eval_run = (
        db.query(SelectionEvalRun)
        .filter(SelectionEvalRun.report_path == report_path)
        .first()
    )
    if eval_run is None:
        eval_run = SelectionEvalRun(
            id=str(uuid.uuid4()),
            user_id=user_id,
            report_path=report_path,
        )
        db.add(eval_run)

    eval_run.user_id = user_id
    eval_run.background_job_id = background_job_id
    eval_run.run_id = str(summary.get("run_id") or "")
    eval_run.dataset_version = _optional_str(summary.get("dataset_version"))
    eval_run.agent_id = int(summary.get("agent_id") or 0)
    eval_run.api_base = _optional_str(summary.get("api_base"))
    eval_run.worker_api_base = _optional_str(summary.get("worker_api_base"))
    eval_run.dry_run = bool(summary.get("dry_run", True))
    eval_run.case_count = int(summary.get("case_count") or 0)
    eval_run.passed = int(summary.get("passed") or 0)
    eval_run.failed = int(summary.get("failed") or 0)
    eval_run.pass_rate = float(summary.get("pass_rate") or 0.0)
    eval_run.by_loop = _optional_dict(summary.get("by_loop"))
    eval_run.budget = _optional_dict(summary.get("budget"))
    summary_with_id = {**_jsonable_dict(summary), "eval_run_id": str(eval_run.id)}
    eval_run.summary_json = summary_with_id
    eval_run.created_at_source = _parse_datetime(summary.get("created_at"))

    db.flush()
    (
        db.query(SelectionEvalResult)
        .filter(SelectionEvalResult.eval_run_id == eval_run.id)
        .delete(synchronize_session=False)
    )
    for result_path in sorted((eval_dir / "results").glob("*.json")):
        result_data = _read_json_dict(result_path)
        db.add(_build_result(eval_run, eval_dir, result_path, result_data))

    db.commit()
    db.refresh(eval_run)
    return eval_run


def create_selection_loop_profile(
    db: Session,
    *,
    user_id: int,
    data: dict[str, Any],
) -> SelectionLoopProfile:
    profile = SelectionLoopProfile(id=str(uuid.uuid4()), user_id=user_id)
    _apply_selection_loop_profile_data(profile, data)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def list_selection_loop_profiles(
    db: Session,
    *,
    user_id: int,
    limit: int,
    offset: int,
    job_family: str | None = None,
    is_active: bool | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    query = db.query(SelectionLoopProfile).filter(SelectionLoopProfile.user_id == user_id)
    if job_family:
        query = query.filter(SelectionLoopProfile.job_family == job_family)
    if is_active is not None:
        query = query.filter(SelectionLoopProfile.is_active.is_(is_active))
    total = query.count()
    profiles = (
        query.order_by(
            SelectionLoopProfile.updated_at.desc(),
            SelectionLoopProfile.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, [serialize_selection_loop_profile(profile) for profile in profiles]


def get_selection_loop_profile(
    db: Session,
    *,
    user_id: int,
    profile_id: str,
) -> SelectionLoopProfile | None:
    return (
        db.query(SelectionLoopProfile)
        .filter(SelectionLoopProfile.id == profile_id, SelectionLoopProfile.user_id == user_id)
        .first()
    )


def update_selection_loop_profile(
    db: Session,
    *,
    profile: SelectionLoopProfile,
    data: dict[str, Any],
) -> SelectionLoopProfile:
    _apply_selection_loop_profile_data(profile, data, partial=True)
    db.commit()
    db.refresh(profile)
    return profile


def delete_selection_loop_profile(db: Session, *, profile: SelectionLoopProfile) -> None:
    db.delete(profile)
    db.commit()


def import_selection_loop_cases(
    db: Session,
    *,
    user_id: int,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    imported: list[SelectionLoopCase] = []
    for record in records:
        case_id = str(record.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("selection loop case record requires case_id")
        dataset_version = _optional_str(record.get("dataset_version"))
        query = db.query(SelectionLoopCase).filter(
            SelectionLoopCase.user_id == user_id,
            SelectionLoopCase.case_id == case_id,
        )
        if dataset_version:
            query = query.filter(SelectionLoopCase.dataset_version == dataset_version)
        else:
            query = query.filter(SelectionLoopCase.dataset_version.is_(None))
        loop_case = query.first()
        if loop_case is None:
            loop_case = SelectionLoopCase(
                id=str(uuid.uuid4()),
                user_id=user_id,
                case_id=case_id,
                dataset_version=dataset_version,
            )
            db.add(loop_case)
        _apply_selection_loop_case_record(loop_case, record)
        imported.append(loop_case)

    db.commit()
    for loop_case in imported:
        db.refresh(loop_case)
    return {
        "imported_count": len(imported),
        "cases": [serialize_selection_loop_case(loop_case) for loop_case in imported],
    }


def list_selection_loop_cases(
    db: Session,
    *,
    user_id: int,
    limit: int,
    offset: int,
    dataset_version: str | None = None,
    loop_type: str | None = None,
    profile_id: str | None = None,
    is_active: bool | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    query = db.query(SelectionLoopCase).filter(SelectionLoopCase.user_id == user_id)
    if dataset_version:
        query = query.filter(SelectionLoopCase.dataset_version == dataset_version)
    if loop_type:
        query = query.filter(SelectionLoopCase.loop_type == loop_type)
    if profile_id:
        query = query.filter(SelectionLoopCase.profile_id == profile_id)
    if is_active is not None:
        query = query.filter(SelectionLoopCase.is_active.is_(is_active))
    total = query.count()
    cases = (
        query.order_by(
            SelectionLoopCase.dataset_version.desc(),
            SelectionLoopCase.loop_type.asc(),
            SelectionLoopCase.case_id.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, [serialize_selection_loop_case(loop_case) for loop_case in cases]


def get_selection_loop_case(
    db: Session,
    *,
    user_id: int,
    loop_case_id: str,
) -> SelectionLoopCase | None:
    return (
        db.query(SelectionLoopCase)
        .filter(SelectionLoopCase.id == loop_case_id, SelectionLoopCase.user_id == user_id)
        .first()
    )


def update_selection_loop_case(
    db: Session,
    *,
    loop_case: SelectionLoopCase,
    data: dict[str, Any],
) -> SelectionLoopCase:
    _apply_selection_loop_case_record(loop_case, data, partial=True)
    db.commit()
    db.refresh(loop_case)
    return loop_case


def delete_selection_loop_case(db: Session, *, loop_case: SelectionLoopCase) -> None:
    db.delete(loop_case)
    db.commit()


def list_loop_eval_runs(
    db: Session,
    *,
    user_id: int,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    query = db.query(SelectionEvalRun).filter(SelectionEvalRun.user_id == user_id)
    total = query.count()
    runs = (
        query.order_by(SelectionEvalRun.updated_at.desc(), SelectionEvalRun.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, [serialize_eval_run(run) for run in runs]


def get_loop_eval_run(
    db: Session,
    *,
    user_id: int,
    eval_run_id: str,
) -> SelectionEvalRun | None:
    return (
        db.query(SelectionEvalRun)
        .filter(SelectionEvalRun.id == eval_run_id, SelectionEvalRun.user_id == user_id)
        .first()
    )


def list_loop_eval_results(
    db: Session,
    *,
    eval_run_id: str,
    limit: int,
    offset: int,
    loop_type: str | None = None,
    passed: bool | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    query = db.query(SelectionEvalResult).filter(
        SelectionEvalResult.eval_run_id == eval_run_id
    )
    if loop_type:
        query = query.filter(SelectionEvalResult.loop_type == loop_type)
    if passed is not None:
        query = query.filter(SelectionEvalResult.passed.is_(passed))
    total = query.count()
    results = (
        query.order_by(SelectionEvalResult.loop_type.asc(), SelectionEvalResult.case_id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, [serialize_eval_result(result) for result in results]


def get_loop_eval_metrics(
    db: Session,
    *,
    user_id: int,
    agent_id: int | None = None,
    dataset_version: str | None = None,
    dry_run: bool | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    recent_limit: int = 10,
) -> dict[str, Any]:
    run_query = _filtered_run_query(
        db,
        user_id=user_id,
        agent_id=agent_id,
        dataset_version=dataset_version,
        dry_run=dry_run,
        created_from=created_from,
        created_to=created_to,
    )
    total_row = run_query.with_entities(
        func.count(SelectionEvalRun.id),
        func.coalesce(func.sum(SelectionEvalRun.case_count), 0),
        func.coalesce(func.sum(SelectionEvalRun.passed), 0),
        func.coalesce(func.sum(SelectionEvalRun.failed), 0),
    ).one()
    run_count = int(total_row[0] or 0)
    case_count = int(total_row[1] or 0)
    passed = int(total_row[2] or 0)
    failed = int(total_row[3] or 0)

    result_query = _filtered_result_query(
        db,
        user_id=user_id,
        agent_id=agent_id,
        dataset_version=dataset_version,
        dry_run=dry_run,
        created_from=created_from,
        created_to=created_to,
    )
    result_count = int(
        result_query.with_entities(func.count(SelectionEvalResult.id)).scalar() or 0
    )

    return {
        "filters": {
            "agent_id": agent_id,
            "dataset_version": dataset_version,
            "dry_run": dry_run,
            "created_from": _isoformat(created_from),
            "created_to": _isoformat(created_to),
        },
        "totals": {
            "run_count": run_count,
            "case_count": case_count,
            "result_count": result_count,
            "passed": passed,
            "failed": failed,
            "pass_rate": _rate(passed, case_count),
        },
        "by_loop": _loop_metrics(result_query),
        "by_dataset": _run_group_metrics(run_query, SelectionEvalRun.dataset_version),
        "by_agent": _run_group_metrics(run_query, SelectionEvalRun.agent_id),
        "by_dry_run": _run_group_metrics(run_query, SelectionEvalRun.dry_run),
        "recent_runs": [
            serialize_eval_run(run)
            for run in run_query.order_by(
                SelectionEvalRun.created_at.desc(), SelectionEvalRun.updated_at.desc()
            )
            .limit(recent_limit)
            .all()
        ],
        "outcomes": get_selection_outcome_metrics(
            db,
            user_id=user_id,
            dataset_version=dataset_version,
            created_from=created_from,
            created_to=created_to,
        ),
    }


def import_selection_outcomes(
    db: Session,
    *,
    user_id: int,
    records: list[dict[str, Any]],
    import_batch_id: str | None = None,
) -> dict[str, Any]:
    batch_id = import_batch_id or str(uuid.uuid4())
    imported: list[SelectionOutcome] = []
    for record in records:
        case_id = str(record.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("selection outcome record requires case_id")

        eval_run_id = _optional_str(record.get("eval_run_id"))
        query = db.query(SelectionOutcome).filter(
            SelectionOutcome.user_id == user_id,
            SelectionOutcome.case_id == case_id,
        )
        if eval_run_id:
            query = query.filter(SelectionOutcome.eval_run_id == eval_run_id)
        else:
            query = query.filter(SelectionOutcome.eval_run_id.is_(None))
        outcome = query.first()
        if outcome is None:
            outcome = SelectionOutcome(
                id=str(uuid.uuid4()),
                user_id=user_id,
                case_id=case_id,
                eval_run_id=eval_run_id,
            )
            db.add(outcome)

        _apply_selection_outcome_record(outcome, record, batch_id)
        imported.append(outcome)

    db.commit()
    for outcome in imported:
        db.refresh(outcome)
    return {
        "import_batch_id": batch_id,
        "imported_count": len(imported),
        "outcomes": [serialize_selection_outcome(outcome) for outcome in imported],
    }


def list_selection_outcomes(
    db: Session,
    *,
    user_id: int,
    limit: int,
    offset: int,
    dataset_version: str | None = None,
    loop_type: str | None = None,
    case_id: str | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    query = db.query(SelectionOutcome).filter(SelectionOutcome.user_id == user_id)
    if dataset_version:
        query = query.filter(SelectionOutcome.dataset_version == dataset_version)
    if loop_type:
        query = query.filter(SelectionOutcome.loop_type == loop_type)
    if case_id:
        query = query.filter(SelectionOutcome.case_id == case_id)
    total = query.count()
    outcomes = (
        query.order_by(SelectionOutcome.updated_at.desc(), SelectionOutcome.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, [serialize_selection_outcome(outcome) for outcome in outcomes]


def get_selection_outcome_metrics(
    db: Session,
    *,
    user_id: int,
    dataset_version: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> dict[str, Any]:
    query = db.query(SelectionOutcome).filter(SelectionOutcome.user_id == user_id)
    if dataset_version:
        query = query.filter(SelectionOutcome.dataset_version == dataset_version)
    if created_from is not None:
        query = query.filter(SelectionOutcome.created_at >= created_from)
    if created_to is not None:
        query = query.filter(SelectionOutcome.created_at <= created_to)
    outcomes = query.all()
    confusion = _outcome_confusion(outcomes)
    return {
        "outcome_count": len(outcomes),
        "by_actual_outcome": _outcome_group_counts(outcomes, "actual_outcome"),
        "by_agent_recommendation": _outcome_group_counts(outcomes, "agent_recommendation"),
        "confusion": confusion,
    }


def serialize_eval_run(run: SelectionEvalRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "user_id": run.user_id,
        "background_job_id": run.background_job_id,
        "run_id": run.run_id,
        "dataset_version": run.dataset_version,
        "agent_id": run.agent_id,
        "api_base": run.api_base,
        "worker_api_base": run.worker_api_base,
        "dry_run": run.dry_run,
        "case_count": run.case_count,
        "passed": run.passed,
        "failed": run.failed,
        "pass_rate": run.pass_rate,
        "report_path": run.report_path,
        "by_loop": run.by_loop or {},
        "budget": run.budget or {},
        "summary": run.summary_json or {},
        "created_at_source": _isoformat(run.created_at_source),
        "created_at": _isoformat(run.created_at),
        "updated_at": _isoformat(run.updated_at),
    }


def serialize_eval_result(result: SelectionEvalResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "eval_run_id": result.eval_run_id,
        "case_id": result.case_id,
        "loop_type": result.loop_type,
        "dataset_version": result.dataset_version,
        "task_id": result.task_id,
        "passed": result.passed,
        "score": result.score,
        "transport": result.transport or {},
        "judge": result.judge or {},
        "tags": result.tags or {},
        "result": result.result_json or {},
        "result_path": result.result_path,
        "raw_output_path": result.raw_output_path,
        "failed_case_path": result.failed_case_path,
        "created_at": _isoformat(result.created_at),
        "updated_at": _isoformat(result.updated_at),
    }


def serialize_selection_loop_profile(profile: SelectionLoopProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "user_id": profile.user_id,
        "name": profile.name,
        "job_family": profile.job_family,
        "job_title": profile.job_title,
        "level": profile.level,
        "locale": profile.locale,
        "profile": profile.profile_json or {},
        "source_type": profile.source_type,
        "privacy_level": profile.privacy_level,
        "synthetic": profile.synthetic,
        "version": profile.version,
        "is_active": profile.is_active,
        "created_at": _isoformat(profile.created_at),
        "updated_at": _isoformat(profile.updated_at),
    }


def serialize_selection_loop_case(loop_case: SelectionLoopCase) -> dict[str, Any]:
    return {
        "id": loop_case.id,
        "user_id": loop_case.user_id,
        "profile_id": loop_case.profile_id,
        "case_id": loop_case.case_id,
        "loop_type": loop_case.loop_type,
        "dataset_version": loop_case.dataset_version,
        "case_path": loop_case.case_path,
        "prompt_path": loop_case.prompt_path,
        "prompt_text": loop_case.prompt_text,
        "quality_passed": loop_case.quality_passed,
        "tags": loop_case.tags or {},
        "expected_output": loop_case.expected_output or {},
        "case": loop_case.case_json or {},
        "source_type": loop_case.source_type,
        "privacy_level": loop_case.privacy_level,
        "synthetic": loop_case.synthetic,
        "version": loop_case.version,
        "is_active": loop_case.is_active,
        "created_at": _isoformat(loop_case.created_at),
        "updated_at": _isoformat(loop_case.updated_at),
    }


def serialize_selection_outcome(outcome: SelectionOutcome) -> dict[str, Any]:
    return {
        "id": outcome.id,
        "user_id": outcome.user_id,
        "eval_run_id": outcome.eval_run_id,
        "case_id": outcome.case_id,
        "candidate_id": outcome.candidate_id,
        "loop_type": outcome.loop_type,
        "dataset_version": outcome.dataset_version,
        "agent_recommendation": outcome.agent_recommendation,
        "actual_outcome": outcome.actual_outcome,
        "hired": outcome.hired,
        "offer_accepted": outcome.offer_accepted,
        "performance_rating": outcome.performance_rating,
        "retention_days": outcome.retention_days,
        "outcome_date": _isoformat(outcome.outcome_date),
        "source_type": outcome.source_type,
        "privacy_level": outcome.privacy_level,
        "synthetic": outcome.synthetic,
        "import_batch_id": outcome.import_batch_id,
        "version": outcome.version,
        "notes": outcome.notes,
        "metadata": outcome.metadata_json or {},
        "created_at": _isoformat(outcome.created_at),
        "updated_at": _isoformat(outcome.updated_at),
    }


def _build_result(
    eval_run: SelectionEvalRun,
    eval_dir: Path,
    result_path: Path,
    result_data: dict[str, Any],
) -> SelectionEvalResult:
    case_id = str(result_data.get("case_id") or result_path.stem)
    judge = _optional_dict(result_data.get("judge")) or {}
    transport = _optional_dict(result_data.get("transport")) or {}
    task_id = transport.get("task_id")
    raw_output_path = eval_dir / "raw_outputs" / f"{case_id}.json"
    failed_case_path = eval_dir / "failed_cases" / f"{case_id}.json"
    return SelectionEvalResult(
        eval_run_id=eval_run.id,
        case_id=case_id,
        loop_type=_optional_str(result_data.get("loop_type")),
        dataset_version=_optional_str(result_data.get("dataset_version")),
        task_id=int(task_id) if task_id is not None else None,
        passed=bool(result_data.get("passed") or judge.get("passed")),
        score=float(judge["score"]) if judge.get("score") is not None else None,
        transport=transport,
        judge=judge,
        tags=_optional_dict(result_data.get("tags")),
        result_json=_jsonable_dict(result_data),
        result_path=_relative_path(eval_dir, result_path),
        raw_output_path=_relative_path(eval_dir, raw_output_path)
        if raw_output_path.is_file()
        else None,
        failed_case_path=_relative_path(eval_dir, failed_case_path)
        if failed_case_path.is_file()
        else None,
    )


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _filtered_run_query(
    db: Session,
    *,
    user_id: int,
    agent_id: int | None,
    dataset_version: str | None,
    dry_run: bool | None,
    created_from: datetime | None,
    created_to: datetime | None,
):
    query = db.query(SelectionEvalRun).filter(SelectionEvalRun.user_id == user_id)
    if agent_id is not None:
        query = query.filter(SelectionEvalRun.agent_id == agent_id)
    if dataset_version:
        query = query.filter(SelectionEvalRun.dataset_version == dataset_version)
    if dry_run is not None:
        query = query.filter(SelectionEvalRun.dry_run.is_(dry_run))
    if created_from is not None:
        query = query.filter(SelectionEvalRun.created_at >= created_from)
    if created_to is not None:
        query = query.filter(SelectionEvalRun.created_at <= created_to)
    return query


def _filtered_result_query(
    db: Session,
    *,
    user_id: int,
    agent_id: int | None,
    dataset_version: str | None,
    dry_run: bool | None,
    created_from: datetime | None,
    created_to: datetime | None,
):
    query = db.query(SelectionEvalResult).join(SelectionEvalRun)
    query = query.filter(SelectionEvalRun.user_id == user_id)
    if agent_id is not None:
        query = query.filter(SelectionEvalRun.agent_id == agent_id)
    if dataset_version:
        query = query.filter(SelectionEvalRun.dataset_version == dataset_version)
    if dry_run is not None:
        query = query.filter(SelectionEvalRun.dry_run.is_(dry_run))
    if created_from is not None:
        query = query.filter(SelectionEvalRun.created_at >= created_from)
    if created_to is not None:
        query = query.filter(SelectionEvalRun.created_at <= created_to)
    return query


def _loop_metrics(query) -> list[dict[str, Any]]:
    rows = (
        query.with_entities(
            SelectionEvalResult.loop_type,
            func.count(SelectionEvalResult.id),
            func.coalesce(
                func.sum(case((SelectionEvalResult.passed.is_(True), 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((SelectionEvalResult.passed.is_(False), 1), else_=0)),
                0,
            ),
        )
        .group_by(SelectionEvalResult.loop_type)
        .order_by(SelectionEvalResult.loop_type.asc())
        .all()
    )
    return [
        {
            "loop_type": row[0] or "unknown",
            "result_count": int(row[1] or 0),
            "passed": int(row[2] or 0),
            "failed": int(row[3] or 0),
            "pass_rate": _rate(int(row[2] or 0), int(row[1] or 0)),
        }
        for row in rows
    ]


def _run_group_metrics(query, group_column) -> list[dict[str, Any]]:
    rows = (
        query.with_entities(
            group_column,
            func.count(SelectionEvalRun.id),
            func.coalesce(func.sum(SelectionEvalRun.case_count), 0),
            func.coalesce(func.sum(SelectionEvalRun.passed), 0),
            func.coalesce(func.sum(SelectionEvalRun.failed), 0),
        )
        .group_by(group_column)
        .order_by(group_column.asc())
        .all()
    )
    return [
        {
            "key": row[0],
            "run_count": int(row[1] or 0),
            "case_count": int(row[2] or 0),
            "passed": int(row[3] or 0),
            "failed": int(row[4] or 0),
            "pass_rate": _rate(int(row[3] or 0), int(row[2] or 0)),
        }
        for row in rows
    ]


def _apply_selection_loop_profile_data(
    profile: SelectionLoopProfile,
    data: dict[str, Any],
    *,
    partial: bool = False,
) -> None:
    if not partial or "name" in data:
        name = _optional_str(data.get("name"))
        if not name:
            raise ValueError("selection loop profile requires name")
        profile.name = name
    for attr, key in [
        ("job_family", "job_family"),
        ("job_title", "job_title"),
        ("level", "level"),
        ("locale", "locale"),
        ("source_type", "source_type"),
        ("privacy_level", "privacy_level"),
    ]:
        if not partial or key in data:
            setattr(profile, attr, _optional_str(data.get(key)))
    if not partial or "profile" in data or "profile_json" in data:
        profile.profile_json = _optional_dict(data.get("profile")) or _optional_dict(
            data.get("profile_json")
        ) or {}
    if not partial or "source_type" in data:
        profile.source_type = profile.source_type or "manual"
    if not partial or "privacy_level" in data:
        profile.privacy_level = profile.privacy_level or "synthetic"
    if not partial or "synthetic" in data:
        synthetic = _optional_bool(data.get("synthetic"))
        profile.synthetic = True if synthetic is None else synthetic
    if not partial or "version" in data:
        profile.version = _optional_int(data.get("version")) or 1
    if not partial or "is_active" in data:
        is_active = _optional_bool(data.get("is_active"))
        profile.is_active = True if is_active is None else is_active


def _apply_selection_loop_case_record(
    loop_case: SelectionLoopCase,
    record: dict[str, Any],
    *,
    partial: bool = False,
) -> None:
    if not partial or "case_id" in record:
        case_id = _optional_str(record.get("case_id"))
        if not case_id:
            raise ValueError("selection loop case record requires case_id")
        loop_case.case_id = case_id
    for attr, key in [
        ("profile_id", "profile_id"),
        ("loop_type", "loop_type"),
        ("dataset_version", "dataset_version"),
        ("case_path", "case_path"),
        ("prompt_path", "prompt_path"),
        ("prompt_text", "prompt_text"),
        ("source_type", "source_type"),
        ("privacy_level", "privacy_level"),
    ]:
        if not partial or key in record:
            setattr(loop_case, attr, _optional_str(record.get(key)))
    if not partial or "quality_passed" in record:
        loop_case.quality_passed = _optional_bool(record.get("quality_passed"))
    if not partial or "tags" in record:
        loop_case.tags = _optional_dict(record.get("tags")) or {}
    if not partial or "expected_output" in record:
        loop_case.expected_output = _optional_dict(record.get("expected_output")) or {}
    if not partial or "case" in record or "case_json" in record:
        loop_case.case_json = _optional_dict(record.get("case")) or _optional_dict(
            record.get("case_json")
        ) or {}
    if not partial or "source_type" in record:
        loop_case.source_type = loop_case.source_type or "generated"
    if not partial or "privacy_level" in record:
        loop_case.privacy_level = loop_case.privacy_level or "synthetic"
    if not partial or "synthetic" in record:
        synthetic = _optional_bool(record.get("synthetic"))
        loop_case.synthetic = True if synthetic is None else synthetic
    if not partial or "version" in record:
        loop_case.version = _optional_int(record.get("version")) or 1
    if not partial or "is_active" in record:
        is_active = _optional_bool(record.get("is_active"))
        loop_case.is_active = True if is_active is None else is_active


def _apply_selection_outcome_record(
    outcome: SelectionOutcome,
    record: dict[str, Any],
    import_batch_id: str,
) -> None:
    outcome.candidate_id = _optional_str(record.get("candidate_id"))
    outcome.loop_type = _optional_str(record.get("loop_type"))
    outcome.dataset_version = _optional_str(record.get("dataset_version"))
    outcome.agent_recommendation = _normalize_label(record.get("agent_recommendation"))
    outcome.actual_outcome = _normalize_label(record.get("actual_outcome"))
    outcome.hired = _optional_bool(record.get("hired"))
    outcome.offer_accepted = _optional_bool(record.get("offer_accepted"))
    outcome.performance_rating = _optional_float(record.get("performance_rating"))
    outcome.retention_days = _optional_int(record.get("retention_days"))
    outcome.outcome_date = _parse_datetime(record.get("outcome_date"))
    outcome.source_type = _optional_str(record.get("source_type")) or "manual_import"
    outcome.privacy_level = _optional_str(record.get("privacy_level")) or "synthetic"
    outcome.synthetic = _optional_bool(record.get("synthetic"))
    if outcome.synthetic is None:
        outcome.synthetic = True
    outcome.import_batch_id = import_batch_id
    outcome.version = _optional_int(record.get("version")) or 1
    outcome.notes = _optional_str(record.get("notes"))
    outcome.metadata_json = _optional_dict(record.get("metadata")) or _optional_dict(
        record.get("metadata_json")
    )


def _outcome_group_counts(
    outcomes: list[SelectionOutcome],
    attr_name: str,
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        key = getattr(outcome, attr_name) or "unknown"
        counts[str(key)] = counts.get(str(key), 0) + 1
    return [{"key": key, "count": counts[key]} for key in sorted(counts)]


def _outcome_confusion(outcomes: list[SelectionOutcome]) -> dict[str, Any]:
    true_positive = true_negative = false_positive = false_negative = skipped = 0
    for outcome in outcomes:
        recommendation = _recommendation_bool(outcome.agent_recommendation)
        success = _actual_success_bool(outcome)
        if recommendation is None or success is None:
            skipped += 1
            continue
        if recommendation and success:
            true_positive += 1
        elif recommendation and not success:
            false_positive += 1
        elif not recommendation and success:
            false_negative += 1
        else:
            true_negative += 1

    evaluated = true_positive + true_negative + false_positive + false_negative
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    return {
        "evaluated": evaluated,
        "skipped": skipped,
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "false_positive_rate": _rate(false_positive, false_positive + true_negative),
        "false_negative_rate": _rate(false_negative, false_negative + true_positive),
        "precision": _rate(true_positive, precision_denominator),
        "recall": _rate(true_positive, recall_denominator),
    }


def _recommendation_bool(value: Any) -> bool | None:
    label = _normalize_label(value)
    if label in {"hire", "recommend", "strong_hire", "advance", "yes"}:
        return True
    if label in {"no_hire", "reject", "do_not_hire", "no", "hold"}:
        return False
    return None


def _actual_success_bool(outcome: SelectionOutcome) -> bool | None:
    label = _normalize_label(outcome.actual_outcome)
    if label in {"success", "successful", "strong_success", "pass"}:
        return True
    if label in {"unsuccessful", "failed", "regretted", "bad_hire", "fail"}:
        return False
    if outcome.hired is False:
        return False
    if outcome.hired is True:
        if outcome.performance_rating is not None:
            return outcome.performance_rating >= 3.0
        if outcome.retention_days is not None:
            return outcome.retention_days >= 30
    return None


def _normalize_label(value: Any) -> str | None:
    if value is None:
        return None
    label = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return label or None


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _optional_dict(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _jsonable_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return bool(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
