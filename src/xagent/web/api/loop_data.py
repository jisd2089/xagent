"""Loop data factory API endpoints."""

from __future__ import annotations

import csv
import json
import random
import zipfile
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...config import get_loop_data_dir
from ..auth_dependencies import get_current_user
from ..models.background_job import BackgroundJob, BackgroundJobType
from ..models.database import get_db
from ..models.task import Task, TraceEvent
from ..models.user import User
from ..services.background_jobs import (
    create_background_job,
    enqueue_background_job,
    is_background_job_enqueue_available,
)
from ..services.loop_eval_budget import (
    get_loop_eval_budget_db_status,
    get_loop_eval_budget_status,
    record_loop_eval_budget_counters,
)
from ..services.loop_eval_reports import (
    create_selection_loop_profile,
    delete_selection_loop_case,
    delete_selection_loop_profile,
    get_selection_loop_case,
    get_selection_loop_profile,
    get_loop_eval_run,
    get_loop_eval_metrics,
    get_selection_outcome_metrics,
    import_selection_loop_cases,
    import_selection_outcomes,
    list_selection_loop_cases,
    list_selection_loop_profiles,
    list_selection_outcomes,
    list_loop_eval_results,
    list_loop_eval_runs,
    persist_loop_eval_report,
    serialize_eval_run,
    serialize_selection_loop_case,
    serialize_selection_loop_profile,
    update_selection_loop_case,
    update_selection_loop_profile,
)
from ..services.loop_trace import (
    create_loop_trace_task,
    emit_loop_trace_event,
    safe_loop_eval_trace_payload,
    summarize_dataset_manifest,
    summarize_loop_eval_summary,
)
from ..services.transient_secrets import stash_transient_secret

try:
    from xagent.loop_data_factory.adversarial_mutator import (
        build_mutation_plan_from_coverage,
    )
    from xagent.loop_data_factory.generate_dataset import generate_dataset
    from xagent.loop_data_factory.run_agent31_regression import run_regression
except Exception:  # pragma: no cover - import failure is reported by endpoint.
    build_mutation_plan_from_coverage = None  # type: ignore[assignment]
    generate_dataset = None  # type: ignore[assignment]
    run_regression = None  # type: ignore[assignment]


loop_data_router = APIRouter(prefix="/api/loop-data", tags=["loop-data"])
loop_eval_router = APIRouter(prefix="/api/loop-eval", tags=["loop-eval"])
selection_profiles_router = APIRouter(
    prefix="/api/selection-profiles",
    tags=["selection-profiles"],
)
selection_cases_router = APIRouter(
    prefix="/api/selection-cases",
    tags=["selection-cases"],
)
selection_outcomes_router = APIRouter(
    prefix="/api/selection-outcomes",
    tags=["selection-outcomes"],
)
REPORT_FILE_KINDS = {"results", "raw_outputs", "failed_cases"}
MAX_SELECTION_OUTCOME_CSV_BYTES = 1_000_000
MAX_SELECTION_OUTCOME_CSV_ROWS = 1000
SELECTION_OUTCOME_CSV_FIELDS = {
    "case_id",
    "eval_run_id",
    "candidate_id",
    "loop_type",
    "dataset_version",
    "agent_recommendation",
    "actual_outcome",
    "hired",
    "offer_accepted",
    "performance_rating",
    "retention_days",
    "outcome_date",
    "source_type",
    "privacy_level",
    "synthetic",
    "version",
    "notes",
}
TRACE_REDACT_KEYS = {
    "api_key",
    "api_key_secret_ref",
    "login_password",
    "password",
    "secret",
    "token",
}


class LoopDataGenerateRequest(BaseModel):
    level: Literal["smoke", "mvp", "regression", "production_eval"] = "smoke"
    loops: list[Literal["loop1", "loop2", "loop3"]] | None = None
    output_subdir: str | None = Field(
        None,
        description="Relative directory under XAGENT_LOOP_DATA_DIR. Defaults to generated_<level>.",
    )
    seed_subdir: str | None = Field(
        None,
        description="Optional local seed-material directory under XAGENT_LOOP_DATA_DIR.",
    )
    adversarial_copies: int = Field(
        0,
        ge=0,
        le=5,
        description="Optional deterministic adversarial copies to add per generated case.",
    )
    clean: bool = True
    background: bool = False


class LoopEvalRunRequest(BaseModel):
    dataset_manifest: str = "dataset_manifest.json"
    output_subdir: str | None = None
    agent_id: int = 31
    dry_run: bool = True
    api_base: str = "http://localhost"
    api_key: str | None = None
    login_username: str | None = None
    login_password: str | None = None
    rotate_runtime_key: bool = False
    reuse_task_map: str | None = None
    case_ids: list[str] | None = None
    selection_case_ids: list[str] | None = Field(
        None,
        description="Optional SelectionLoopCase row ids to run. Mutually exclusive with case_ids and sampling filters.",
    )
    selection_profile_id: str | None = Field(
        None,
        description="Optional SelectionLoopProfile id; active cases bound to this profile are used as eval cases.",
    )
    selection_cases_active_only: bool = True
    limit: int | None = Field(None, ge=1, le=200)
    sample_count: int | None = Field(
        None,
        ge=1,
        le=30,
        description="Select a deterministic representative sample before running eval.",
    )
    sample_seed: int = Field(31, ge=0)
    sample_loops: list[Literal["loop1", "loop2", "loop3"]] | None = None
    sample_tags: dict[str, str] | None = Field(
        None,
        description="Optional exact tag filters applied before sampling, for example {'job_family': 'backend_architect'}.",
    )
    max_new_tasks: int = Field(
        3,
        ge=0,
        le=30,
        description="Budget guard for non-dry-run evals that create new SDK tasks.",
    )
    stop_on_failure: bool = False
    timeout_seconds: float = Field(900.0, ge=1.0, le=3600.0)
    poll_interval: float = Field(2.0, ge=0.5, le=60.0)
    clean: bool = True
    background: bool = False


class LoopEvalImportReportsRequest(BaseModel):
    paths: list[str] | None = Field(
        None,
        description="Relative report directories under XAGENT_LOOP_DATA_DIR. Defaults to latest reports.",
    )
    limit: int = Field(50, ge=1, le=200)


class SelectionOutcomeRecord(BaseModel):
    case_id: str
    eval_run_id: str | None = None
    candidate_id: str | None = None
    loop_type: Literal["loop1", "loop2", "loop3"] | None = None
    dataset_version: str | None = None
    agent_recommendation: str | None = None
    actual_outcome: str | None = None
    hired: bool | None = None
    offer_accepted: bool | None = None
    performance_rating: float | None = None
    retention_days: int | None = Field(None, ge=0)
    outcome_date: datetime | None = None
    source_type: str = "manual_import"
    privacy_level: str = "synthetic"
    synthetic: bool = True
    version: int = Field(1, ge=1)
    notes: str | None = None
    metadata: dict[str, Any] | None = None


class SelectionOutcomeImportRequest(BaseModel):
    records: list[SelectionOutcomeRecord] = Field(..., min_length=1, max_length=1000)
    import_batch_id: str | None = None


class SelectionLoopProfileRequest(BaseModel):
    name: str
    job_family: str | None = None
    job_title: str | None = None
    level: str | None = None
    locale: str | None = None
    profile: dict[str, Any] = Field(default_factory=dict)
    source_type: str = "manual"
    privacy_level: str = "synthetic"
    synthetic: bool = True
    version: int = Field(1, ge=1)
    is_active: bool = True


class SelectionLoopProfileUpdateRequest(BaseModel):
    name: str | None = None
    job_family: str | None = None
    job_title: str | None = None
    level: str | None = None
    locale: str | None = None
    profile: dict[str, Any] | None = None
    source_type: str | None = None
    privacy_level: str | None = None
    synthetic: bool | None = None
    version: int | None = Field(None, ge=1)
    is_active: bool | None = None


class SelectionLoopCaseRecord(BaseModel):
    case_id: str
    profile_id: str | None = None
    loop_type: Literal["loop1", "loop2", "loop3"] | None = None
    dataset_version: str | None = None
    case_path: str | None = None
    prompt_path: str | None = None
    prompt_text: str | None = None
    quality_passed: bool | None = None
    tags: dict[str, Any] | None = None
    expected_output: dict[str, Any] | None = None
    case: dict[str, Any] | None = None
    source_type: str = "manual_import"
    privacy_level: str = "synthetic"
    synthetic: bool = True
    version: int = Field(1, ge=1)
    is_active: bool = True


class SelectionLoopCasesImportRequest(BaseModel):
    records: list[SelectionLoopCaseRecord] = Field(..., min_length=1, max_length=1000)


class SelectionLoopCasesImportManifestRequest(BaseModel):
    dataset_manifest: str = "dataset_manifest.json"
    profile_id: str | None = None
    limit: int | None = Field(None, ge=1, le=1000)
    source_type: str = "generated_manifest"
    privacy_level: str = "synthetic"
    synthetic: bool = True


class SelectionLoopCaseUpdateRequest(BaseModel):
    profile_id: str | None = None
    loop_type: Literal["loop1", "loop2", "loop3"] | None = None
    dataset_version: str | None = None
    case_path: str | None = None
    prompt_path: str | None = None
    prompt_text: str | None = None
    quality_passed: bool | None = None
    tags: dict[str, Any] | None = None
    expected_output: dict[str, Any] | None = None
    case: dict[str, Any] | None = None
    source_type: str | None = None
    privacy_level: str | None = None
    synthetic: bool | None = None
    version: int | None = Field(None, ge=1)
    is_active: bool | None = None


@loop_data_router.get("/status")
def get_loop_data_status(_user: User = Depends(get_current_user)) -> dict[str, object]:
    root = get_loop_data_dir()
    manifests = discover_dataset_manifests(root)
    return {
        "loop_data_dir": str(root),
        "exists": root.exists(),
        "manifest_count": len(manifests),
        "manifests": manifests,
        }


@loop_eval_router.get("/reports")
def list_loop_eval_reports(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    root = get_loop_data_dir()
    reports = discover_eval_reports(root)
    return {
        "loop_data_dir": str(root),
        "total": len(reports),
        "limit": limit,
        "offset": offset,
        "reports": reports[offset : offset + limit],
    }


@loop_eval_router.get("/budget/status")
def get_loop_eval_budget(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    status = get_loop_eval_budget_status()
    status["db"] = get_loop_eval_budget_db_status(db, user_id=int(user.id))
    return status


@loop_eval_router.post("/db/import-reports")
def import_loop_eval_db_reports(
    request: LoopEvalImportReportsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    root = get_loop_data_dir()
    paths = request.paths
    if paths is None:
        paths = [
            str(report["path"])
            for report in discover_eval_reports(root)[: request.limit]
            if isinstance(report.get("path"), str)
        ]

    imported: list[dict[str, object]] = []
    for path in paths[: request.limit]:
        report_dir = resolve_loop_report_dir(root, path)
        summary = read_json_file(report_dir / "summary.json")
        if not isinstance(summary, dict):
            raise HTTPException(status_code=500, detail="summary.json must be an object")
        eval_run = persist_loop_eval_report(
            db,
            user_id=int(user.id),
            eval_dir=report_dir,
            summary=summary,
        )
        imported.append(
            {
                "path": path_from_root(root, report_dir),
                "eval_run_id": str(eval_run.id),
                "case_count": int(eval_run.case_count),
            }
        )

    return {
        "loop_data_dir": str(root),
        "imported_count": len(imported),
        "imported": imported,
    }


@loop_eval_router.get("/db/metrics")
def get_loop_eval_db_metrics(
    agent_id: int | None = Query(None, ge=1),
    dataset_version: str | None = None,
    dry_run: bool | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    recent_limit: int = Query(10, ge=0, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return get_loop_eval_metrics(
        db,
        user_id=int(user.id),
        agent_id=agent_id,
        dataset_version=dataset_version,
        dry_run=dry_run,
        created_from=created_from,
        created_to=created_to,
        recent_limit=recent_limit,
    )


@selection_profiles_router.post("")
def create_selection_profile_api(
    request: SelectionLoopProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        profile = create_selection_loop_profile(
            db,
            user_id=int(user.id),
            data=request.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_selection_loop_profile(profile)


@selection_profiles_router.get("")
def list_selection_profiles_api(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    job_family: str | None = None,
    is_active: bool | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    total, profiles = list_selection_loop_profiles(
        db,
        user_id=int(user.id),
        limit=limit,
        offset=offset,
        job_family=job_family,
        is_active=is_active,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "profiles": profiles,
    }


@selection_profiles_router.get("/{profile_id}")
def get_selection_profile_api(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    profile = get_selection_loop_profile(
        db,
        user_id=int(user.id),
        profile_id=profile_id,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="selection profile not found")
    return serialize_selection_loop_profile(profile)


@selection_profiles_router.put("/{profile_id}")
def update_selection_profile_api(
    profile_id: str,
    request: SelectionLoopProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    profile = get_selection_loop_profile(
        db,
        user_id=int(user.id),
        profile_id=profile_id,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="selection profile not found")
    try:
        profile = update_selection_loop_profile(
            db,
            profile=profile,
            data=request.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_selection_loop_profile(profile)


@selection_profiles_router.delete("/{profile_id}")
def delete_selection_profile_api(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    profile = get_selection_loop_profile(
        db,
        user_id=int(user.id),
        profile_id=profile_id,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="selection profile not found")
    delete_selection_loop_profile(db, profile=profile)
    return {"deleted": True, "id": profile_id}


@selection_cases_router.post("/import")
def import_selection_cases_api(
    request: SelectionLoopCasesImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        return import_selection_loop_cases(
            db,
            user_id=int(user.id),
            records=[record.model_dump() for record in request.records],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@selection_cases_router.post("/import-manifest")
def import_selection_cases_manifest_api(
    request: SelectionLoopCasesImportManifestRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    root = get_loop_data_dir()
    manifest_path = resolve_loop_file(root, request.dataset_manifest)
    manifest = read_json_file(manifest_path)
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=500, detail="dataset manifest must be an object")
    records = build_selection_case_records_from_manifest(
        manifest_path,
        manifest,
        profile_id=request.profile_id,
        limit=request.limit,
        source_type=request.source_type,
        privacy_level=request.privacy_level,
        synthetic=request.synthetic,
    )
    try:
        imported = import_selection_loop_cases(
            db,
            user_id=int(user.id),
            records=records,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "dataset_manifest": path_from_root(root, manifest_path),
        **imported,
    }


@selection_cases_router.get("")
def list_selection_cases_api(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    dataset_version: str | None = None,
    loop_type: Literal["loop1", "loop2", "loop3"] | None = None,
    profile_id: str | None = None,
    is_active: bool | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    total, cases = list_selection_loop_cases(
        db,
        user_id=int(user.id),
        limit=limit,
        offset=offset,
        dataset_version=dataset_version,
        loop_type=loop_type,
        profile_id=profile_id,
        is_active=is_active,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "cases": cases,
    }


@selection_cases_router.get("/{loop_case_id}")
def get_selection_case_api(
    loop_case_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    loop_case = get_selection_loop_case(
        db,
        user_id=int(user.id),
        loop_case_id=loop_case_id,
    )
    if loop_case is None:
        raise HTTPException(status_code=404, detail="selection case not found")
    return serialize_selection_loop_case(loop_case)


@selection_cases_router.put("/{loop_case_id}")
def update_selection_case_api(
    loop_case_id: str,
    request: SelectionLoopCaseUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    loop_case = get_selection_loop_case(
        db,
        user_id=int(user.id),
        loop_case_id=loop_case_id,
    )
    if loop_case is None:
        raise HTTPException(status_code=404, detail="selection case not found")
    try:
        loop_case = update_selection_loop_case(
            db,
            loop_case=loop_case,
            data=request.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_selection_loop_case(loop_case)


@selection_cases_router.delete("/{loop_case_id}")
def delete_selection_case_api(
    loop_case_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    loop_case = get_selection_loop_case(
        db,
        user_id=int(user.id),
        loop_case_id=loop_case_id,
    )
    if loop_case is None:
        raise HTTPException(status_code=404, detail="selection case not found")
    delete_selection_loop_case(db, loop_case=loop_case)
    return {"deleted": True, "id": loop_case_id}


@selection_outcomes_router.post("/import")
def import_selection_outcomes_api(
    request: SelectionOutcomeImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return import_selection_outcomes(
        db,
        user_id=int(user.id),
        records=[record.model_dump() for record in request.records],
        import_batch_id=request.import_batch_id,
    )


@selection_outcomes_router.post("/import-csv")
async def import_selection_outcomes_csv_api(
    file: UploadFile = File(...),
    import_batch_id: str | None = Form(None),
    default_dataset_version: str | None = Form(None),
    default_loop_type: Literal["loop1", "loop2", "loop3"] | None = Form(None),
    default_source_type: str = Form("csv_import"),
    default_privacy_level: str = Form("synthetic"),
    default_synthetic: bool = Form(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    raw = await file.read(MAX_SELECTION_OUTCOME_CSV_BYTES + 1)
    if len(raw) > MAX_SELECTION_OUTCOME_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV file is too large")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded") from exc

    try:
        records = parse_selection_outcome_csv(
            text,
            default_dataset_version=default_dataset_version,
            default_loop_type=default_loop_type,
            default_source_type=default_source_type,
            default_privacy_level=default_privacy_level,
            default_synthetic=default_synthetic,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return import_selection_outcomes(
        db,
        user_id=int(user.id),
        records=records,
        import_batch_id=import_batch_id,
    )


@selection_outcomes_router.get("")
def list_selection_outcomes_api(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    dataset_version: str | None = None,
    loop_type: Literal["loop1", "loop2", "loop3"] | None = None,
    case_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    total, outcomes = list_selection_outcomes(
        db,
        user_id=int(user.id),
        limit=limit,
        offset=offset,
        dataset_version=dataset_version,
        loop_type=loop_type,
        case_id=case_id,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "outcomes": outcomes,
    }


@selection_outcomes_router.get("/metrics")
def get_selection_outcome_metrics_api(
    dataset_version: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return get_selection_outcome_metrics(
        db,
        user_id=int(user.id),
        dataset_version=dataset_version,
        created_from=created_from,
        created_to=created_to,
    )


@loop_eval_router.get("/db/runs")
def list_loop_eval_db_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    total, runs = list_loop_eval_runs(
        db,
        user_id=int(user.id),
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "runs": runs,
    }


@loop_eval_router.get("/db/runs/{eval_run_id}")
def get_loop_eval_db_run(
    eval_run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    eval_run = get_loop_eval_run(db, user_id=int(user.id), eval_run_id=eval_run_id)
    if eval_run is None:
        raise HTTPException(status_code=404, detail="loop eval run not found")
    return serialize_eval_run(eval_run)


@loop_eval_router.get("/db/runs/{eval_run_id}/results")
def list_loop_eval_db_results(
    eval_run_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    loop_type: Literal["loop1", "loop2", "loop3"] | None = None,
    passed: bool | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    eval_run = get_loop_eval_run(db, user_id=int(user.id), eval_run_id=eval_run_id)
    if eval_run is None:
        raise HTTPException(status_code=404, detail="loop eval run not found")
    total, results = list_loop_eval_results(
        db,
        eval_run_id=str(eval_run.id),
        limit=limit,
        offset=offset,
        loop_type=loop_type,
        passed=passed,
    )
    return {
        "eval_run_id": str(eval_run.id),
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": results,
    }


@loop_eval_router.get("/db/runs/{eval_run_id}/trace")
def get_loop_eval_db_trace(
    eval_run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    eval_run = get_loop_eval_run(db, user_id=int(user.id), eval_run_id=eval_run_id)
    if eval_run is None:
        raise HTTPException(status_code=404, detail="loop eval run not found")

    trace_task_id = resolve_eval_run_trace_task_id(db, eval_run)
    if trace_task_id is None:
        return {
            "eval_run_id": str(eval_run.id),
            "trace_task_id": None,
            "task": None,
            "total": 0,
            "events": [],
        }

    task = (
        db.query(Task)
        .filter(Task.id == trace_task_id, Task.user_id == int(user.id))
        .first()
    )
    if task is None:
        return {
            "eval_run_id": str(eval_run.id),
            "trace_task_id": trace_task_id,
            "task": None,
            "total": 0,
            "events": [],
        }

    events = (
        db.query(TraceEvent)
        .filter(TraceEvent.task_id == trace_task_id)
        .order_by(TraceEvent.timestamp.asc(), TraceEvent.id.asc())
        .all()
    )
    return {
        "eval_run_id": str(eval_run.id),
        "trace_task_id": trace_task_id,
        "task": {
            "id": int(task.id),
            "title": task.title,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "is_visible": bool(task.is_visible),
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        },
        "total": len(events),
        "events": [serialize_trace_event(event) for event in events],
    }


@loop_eval_router.get("/reports/summary")
def get_loop_eval_report_summary(
    path: str = Query(..., description="Relative report directory under XAGENT_LOOP_DATA_DIR."),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    root = get_loop_data_dir()
    report_dir = resolve_loop_report_dir(root, path)
    summary = read_json_file(report_dir / "summary.json")
    eval_manifest = (
        read_json_file(report_dir / "eval_manifest.json")
        if (report_dir / "eval_manifest.json").is_file()
        else None
    )
    return {
        "loop_data_dir": str(root),
        "path": path_from_root(root, report_dir),
        "summary": summary,
        "eval_manifest": eval_manifest,
        "files": list_report_files(report_dir),
    }


@loop_eval_router.get("/reports/files")
def list_loop_eval_report_files(
    path: str = Query(..., description="Relative report directory under XAGENT_LOOP_DATA_DIR."),
    kind: Literal["results", "raw_outputs", "failed_cases"] | None = None,
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    root = get_loop_data_dir()
    report_dir = resolve_loop_report_dir(root, path)
    return {
        "loop_data_dir": str(root),
        "path": path_from_root(root, report_dir),
        "kind": kind,
        "files": list_report_files(report_dir, kind=kind),
    }


@loop_eval_router.get("/reports/file")
def get_loop_eval_report_file(
    path: str = Query(..., description="Relative report directory under XAGENT_LOOP_DATA_DIR."),
    file: str = Query(..., description="Relative JSON file under the report directory."),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    root = get_loop_data_dir()
    report_dir = resolve_loop_report_dir(root, path)
    file_path = resolve_loop_report_file(report_dir, file)
    return {
        "loop_data_dir": str(root),
        "path": path_from_root(root, report_dir),
        "file": path_from_root(report_dir, file_path),
        "content": read_json_file(file_path),
    }


@loop_eval_router.get("/reports/download", response_model=None)
def download_loop_eval_report_file(
    path: str = Query(..., description="Relative report directory under XAGENT_LOOP_DATA_DIR."),
    file: str = Query(..., description="Relative JSON file under the report directory."),
    _user: User = Depends(get_current_user),
) -> FileResponse:
    root = get_loop_data_dir()
    report_dir = resolve_loop_report_dir(root, path)
    file_path = resolve_loop_report_file(report_dir, file)
    return FileResponse(
        file_path,
        media_type="application/json",
        filename=file_path.name,
    )


@loop_eval_router.get("/reports/failed-cases/archive", response_model=None)
def download_loop_eval_failed_cases_archive(
    path: str = Query(..., description="Relative report directory under XAGENT_LOOP_DATA_DIR."),
    _user: User = Depends(get_current_user),
) -> StreamingResponse:
    root = get_loop_data_dir()
    report_dir = resolve_loop_report_dir(root, path)
    archive = build_failed_cases_archive(report_dir)
    filename = f"{report_dir.name or 'loop_eval'}_failed_cases.zip"
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@loop_data_router.post("/eval/run")
@loop_eval_router.post("/run")
def run_loop_eval(
    request: LoopEvalRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if run_regression is None:
        raise HTTPException(status_code=500, detail="Loop regression runner is unavailable")
    if not request.dry_run and not (
        request.api_key or (request.login_username and request.login_password)
    ):
        raise HTTPException(
            status_code=400,
            detail="non-dry-run eval requires api_key or login_username/login_password",
        )

    root = get_loop_data_dir()
    dataset_manifest = resolve_loop_file(root, request.dataset_manifest)
    output_dir = resolve_loop_output_dir(
        root,
        request.output_subdir,
        "eval",
    )
    reuse_task_map = (
        resolve_loop_file(root, request.reuse_task_map)
        if request.reuse_task_map
        else None
    )
    selected_case_ids = resolve_loop_eval_case_ids(
        db,
        user_id=int(user.id),
        request=request,
        dataset_manifest=dataset_manifest,
    )
    trace_task = create_loop_trace_task(
        db,
        user_id=int(user.id),
        title=f"Loop Eval Agent {request.agent_id}",
        description=f"Loop eval for {dataset_manifest.name}",
        agent_id=request.agent_id,
    )
    payload = build_loop_eval_payload(
        request=request,
        dataset_manifest=dataset_manifest,
        output_dir=output_dir,
        reuse_task_map=reuse_task_map,
        selected_case_ids=selected_case_ids,
    )
    payload["trace_task_id"] = int(trace_task.id)
    new_task_count = estimate_new_task_count(
        dataset_manifest,
        selected_case_ids=selected_case_ids,
        limit=request.limit,
        reuse_task_map=payload.get("reuse_task_map"),
        dry_run=request.dry_run,
    )
    if not request.dry_run and new_task_count > request.max_new_tasks:
        budget_scope = loop_eval_budget_scope(request.agent_id)
        record_loop_eval_budget_counters(
            db,
            user_id=int(user.id),
            scope=budget_scope,
            counters={"jobs_rejected_budget": 1},
            metadata={
                "reason": "max_new_tasks",
                "new_task_count": new_task_count,
                "max_new_tasks": request.max_new_tasks,
                "dataset_manifest": str(dataset_manifest),
            },
        )
        emit_loop_trace_event(
            db,
            task_id=int(trace_task.id),
            event_name="budget_guard",
            step_id="loop_eval_budget_guard",
            data={
                "allowed": False,
                "new_task_count": new_task_count,
                "max_new_tasks": request.max_new_tasks,
                "dry_run": request.dry_run,
                "dataset_manifest": str(dataset_manifest),
            },
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Refusing to create {new_task_count} new SDK task(s); "
                f"max_new_tasks={request.max_new_tasks}. Use sample_count, case_ids, "
                "limit, reuse_task_map, or raise max_new_tasks intentionally."
            ),
        )
    payload["budget"] = {
        "new_task_count": new_task_count,
        "max_new_tasks": request.max_new_tasks,
        "stop_on_failure": request.stop_on_failure,
        "scope": loop_eval_budget_scope(request.agent_id),
    }
    emit_loop_trace_event(
        db,
        task_id=int(trace_task.id),
        event_name="loop_eval_selected",
        step_id="loop_eval_selected",
        data={
            **safe_loop_eval_trace_payload(payload),
            "new_task_count": new_task_count,
            "max_new_tasks": request.max_new_tasks,
        },
    )
    if request.background:
        if not request.dry_run and not request.api_key:
            raise HTTPException(
                status_code=400,
                detail=(
                    "background non-dry-run loop eval requires api_key; "
                    "login credentials are not accepted for background jobs"
                ),
            )
        if not request.dry_run:
            payload["api_key_secret_ref"] = stash_transient_secret(
                request.api_key or "",
                namespace="loop-eval-api-key",
                ttl_seconds=int(request.timeout_seconds) + 600,
            )
            payload["worker_api_base"] = default_worker_api_base(request.api_base)
            payload["api_key"] = None
            payload["login_username"] = None
            payload["login_password"] = None
        if not is_background_job_enqueue_available(check_worker=True):
            raise HTTPException(
                status_code=503,
                detail="Background loop eval requires an available Celery worker",
            )
        job = create_background_job(
            db,
            user_id=int(user.id),
            job_type=BackgroundJobType.LOOP_EVAL_RUN,
            payload=payload,
            reuse_terminal_idempotency_key=False,
        )
        job = enqueue_background_job(db, job)
        emit_loop_trace_event(
            db,
            task_id=int(trace_task.id),
            event_name="loop_eval_enqueued",
            step_id="loop_eval_enqueued",
            data={
                "job_id": str(job.id),
                "job_status": str(job.status),
                "queue": str(job.queue),
            },
        )
        return {
            "mode": "background",
            "job_id": str(job.id),
            "trace_task_id": int(trace_task.id),
            "job_status": str(job.status),
            "queue": str(job.queue),
            "loop_data_dir": str(root),
            "dataset_manifest": str(dataset_manifest),
            "output_dir": str(output_dir),
            "selected_case_ids": selected_case_ids,
            "new_task_count": new_task_count,
            "max_new_tasks": request.max_new_tasks,
        }

    sync_budget_recorded = False
    try:
        if not request.dry_run and new_task_count > 0:
            record_loop_eval_budget_counters(
                db,
                user_id=int(user.id),
                scope=loop_eval_budget_scope(request.agent_id),
                counters={
                    "jobs_started": 1,
                    "new_tasks_planned": new_task_count,
                },
                metadata={
                    "mode": "sync",
                    "dataset_manifest": str(dataset_manifest),
                },
            )
            sync_budget_recorded = True
        emit_loop_trace_event(
            db,
            task_id=int(trace_task.id),
            event_name="loop_eval_run_started",
            step_id="loop_eval_run",
            data=safe_loop_eval_trace_payload(payload),
        )
        summary = run_regression(
            dataset_manifest=dataset_manifest,
            agent_id=request.agent_id,
            output_dir=output_dir,
            api_base=request.api_base,
            api_key=request.api_key,
            login_username=request.login_username,
            login_password=request.login_password,
            rotate_runtime_key=request.rotate_runtime_key,
            reuse_task_map=_load_reuse_task_map(reuse_task_map) if reuse_task_map else None,
            dry_run=request.dry_run,
            case_ids=selected_case_ids,
            limit=request.limit,
            max_new_tasks=request.max_new_tasks,
            stop_on_failure=request.stop_on_failure,
            poll_interval=request.poll_interval,
            timeout_seconds=request.timeout_seconds,
            clean=request.clean,
        )
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        if sync_budget_recorded:
            record_loop_eval_budget_counters(
                db,
                user_id=int(user.id),
                scope=loop_eval_budget_scope(request.agent_id),
                counters={"jobs_failed": 1},
                metadata={"error_type": type(exc).__name__},
            )
        emit_loop_trace_event(
            db,
            task_id=int(trace_task.id),
            event_name="loop_eval_failed",
            step_id="loop_eval_run",
            data={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    summary["budget"] = {
        "new_task_count": new_task_count,
        "max_new_tasks": request.max_new_tasks,
        "stop_on_failure": request.stop_on_failure,
        "scope": loop_eval_budget_scope(request.agent_id),
    }
    if sync_budget_recorded:
        record_loop_eval_budget_counters(
            db,
            user_id=int(user.id),
            scope=loop_eval_budget_scope(request.agent_id),
            counters={
                "jobs_succeeded": 1,
                "new_tasks_completed": int(summary.get("new_task_count") or 0),
            },
            metadata={
                "mode": "sync",
                "eval_dir": str(summary.get("eval_dir") or output_dir),
            },
        )
    eval_run = persist_loop_eval_report(
        db,
        user_id=int(user.id),
        eval_dir=Path(str(summary.get("eval_dir") or output_dir)),
        summary=summary,
    )
    summary["eval_run_id"] = str(eval_run.id)
    emit_loop_trace_event(
        db,
        task_id=int(trace_task.id),
        event_name="loop_eval_completed",
        step_id="loop_eval_completed",
        data=summarize_loop_eval_summary(summary),
    )

    return {
        "loop_data_dir": str(root),
        "trace_task_id": int(trace_task.id),
        "dataset_manifest": str(dataset_manifest),
        "output_dir": str(output_dir),
        "selected_case_ids": selected_case_ids,
        "new_task_count": new_task_count,
        "max_new_tasks": request.max_new_tasks,
        "eval_run_id": str(eval_run.id),
        **summary,
    }


@loop_data_router.post("/generate")
def generate_loop_data(
    request: LoopDataGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if generate_dataset is None:
        raise HTTPException(status_code=500, detail="Loop data factory is unavailable")

    root = get_loop_data_dir()
    output_dir = resolve_loop_output_dir(root, request.output_subdir, request.level)
    seed_dir = resolve_optional_loop_dir(root, request.seed_subdir)
    trace_task = create_loop_trace_task(
        db,
        user_id=int(user.id),
        title=f"Loop Data Generate {request.level}",
        description=f"Generate loop data under {output_dir}",
    )

    payload = build_loop_data_generate_payload(
        request=request,
        output_dir=output_dir,
        seed_dir=seed_dir,
        trace_task_id=int(trace_task.id),
    )
    if request.background:
        if not is_background_job_enqueue_available(check_worker=True):
            raise HTTPException(status_code=503, detail="background worker is unavailable")
        job = create_background_job(
            db,
            user_id=int(user.id),
            job_type=BackgroundJobType.LOOP_DATA_GENERATE,
            payload=payload,
            max_attempts=1,
        )
        job = enqueue_background_job(db, job)
        emit_loop_trace_event(
            db,
            task_id=int(trace_task.id),
            event_name="dataset_generation_enqueued",
            step_id="dataset_generation",
            data={
                "job_id": str(job.id),
                "level": request.level,
                "loops": request.loops,
                "output_dir": str(output_dir),
                "seed_dir": str(seed_dir) if seed_dir else None,
                "clean": request.clean,
                "adversarial_copies": request.adversarial_copies,
            },
        )
        return {
            "mode": "background",
            "loop_data_dir": str(root),
            "trace_task_id": int(trace_task.id),
            "job_id": str(job.id),
            "status": job.status,
            "output_dir": str(output_dir),
            "seed_dir": str(seed_dir) if seed_dir else None,
            "adversarial_copies": request.adversarial_copies,
        }

    emit_loop_trace_event(
        db,
        task_id=int(trace_task.id),
        event_name="dataset_generation_started",
        step_id="dataset_generation",
        data={
            "level": request.level,
            "loops": request.loops,
            "output_dir": str(output_dir),
            "seed_dir": str(seed_dir) if seed_dir else None,
            "clean": request.clean,
            "adversarial_copies": request.adversarial_copies,
        },
    )
    try:
        result = run_loop_data_generation_payload(payload)
    except (OSError, ValueError) as exc:
        emit_loop_trace_event(
            db,
            task_id=int(trace_task.id),
            event_name="dataset_generation_failed",
            step_id="dataset_generation",
            data={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    emit_loop_trace_event(
        db,
        task_id=int(trace_task.id),
        event_name="dataset_generation_completed",
        step_id="dataset_generation",
        data=summarize_dataset_manifest(
            result,
            coverage_report=str(result["coverage_report"]),
        ),
    )

    return {
        "mode": "sync",
        "loop_data_dir": str(root),
        "trace_task_id": int(trace_task.id),
        **result,
    }


def build_loop_data_generate_payload(
    *,
    request: LoopDataGenerateRequest,
    output_dir: Path,
    seed_dir: Path | None,
    trace_task_id: int | None = None,
) -> dict[str, object]:
    return {
        "level": request.level,
        "loops": list(request.loops) if request.loops else None,
        "output_dir": str(output_dir),
        "seed_dir": str(seed_dir) if seed_dir else None,
        "clean": request.clean,
        "adversarial_copies_per_case": request.adversarial_copies,
        "trace_task_id": trace_task_id,
    }


def run_loop_data_generation_payload(payload: dict[str, object]) -> dict[str, object]:
    if generate_dataset is None:
        raise RuntimeError("Loop data factory is unavailable")
    output_dir = Path(str(payload["output_dir"]))
    seed_dir_value = payload.get("seed_dir")
    seed_dir = Path(str(seed_dir_value)) if seed_dir_value else None
    manifest = generate_dataset(
        level=str(payload.get("level") or "smoke"),
        output_dir=output_dir,
        loops=_coerce_optional_str_list(payload.get("loops")),
        clean=bool(payload.get("clean", True)),
        seed_dir=seed_dir,
        adversarial_copies_per_case=int(payload.get("adversarial_copies_per_case") or 0),
    )
    coverage_report = str(output_dir / str(manifest["coverage_report"]))
    coverage = read_json_file(Path(coverage_report))
    mutation_plan: list[dict[str, object]] = []
    if isinstance(coverage, dict) and build_mutation_plan_from_coverage is not None:
        mutation_plan = build_mutation_plan_from_coverage(coverage)
    return summarize_loop_data_generation_result(
        output_dir=output_dir,
        manifest=manifest,
        coverage_report=coverage_report,
        mutation_plan=mutation_plan,
    )


def summarize_loop_data_generation_result(
    *,
    output_dir: Path,
    manifest: dict[str, object],
    coverage_report: str,
    mutation_plan: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "output_dir": str(output_dir),
        "manifest_path": str(output_dir / "dataset_manifest.json"),
        "dataset_version": manifest["dataset_version"],
        "level": manifest["level"],
        "loops": manifest["loops"],
        "case_count": manifest["case_count"],
        "coverage_report": coverage_report,
        "mutation_plan": mutation_plan or [],
    }
    for key in ("local_seed_manifest", "local_seed_summary", "adversarial"):
        if key in manifest:
            result[key] = manifest[key]
    return result


def _coerce_optional_str_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("loops must be a list")
    return [str(item) for item in value]


def resolve_loop_output_dir(root: Path, output_subdir: str | None, level: str) -> Path:
    subdir = (output_subdir or f"generated_{level}").strip()
    if not subdir:
        subdir = f"generated_{level}"
    candidate = (root / subdir).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise HTTPException(status_code=400, detail="output_subdir must stay under loop_data_dir")
    return candidate


def resolve_optional_loop_dir(root: Path, relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    candidate = resolve_loop_file(root, relative_path)
    if candidate.exists() and not candidate.is_dir():
        raise HTTPException(status_code=400, detail="seed_subdir must be a directory")
    return candidate


def resolve_loop_file(root: Path, relative_path: str | None) -> Path:
    if not relative_path:
        raise HTTPException(status_code=400, detail="path is required")
    candidate = (root / relative_path).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise HTTPException(status_code=400, detail="path must stay under loop_data_dir")
    return candidate


def resolve_loop_report_dir(root: Path, relative_path: str) -> Path:
    candidate = resolve_loop_file(root, relative_path)
    if not candidate.is_dir():
        raise HTTPException(status_code=404, detail="report directory not found")
    if not (candidate / "summary.json").is_file():
        raise HTTPException(status_code=404, detail="summary.json not found")
    return candidate


def resolve_loop_report_file(report_dir: Path, relative_path: str) -> Path:
    candidate = (report_dir / relative_path).resolve()
    resolved_report_dir = report_dir.resolve()
    if candidate != resolved_report_dir and resolved_report_dir not in candidate.parents:
        raise HTTPException(status_code=400, detail="file must stay under report directory")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="report file not found")
    if candidate.suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="only JSON report files can be read")
    return candidate


def read_json_file(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"invalid JSON report file: {path.name}") from exc
    except OSError as exc:
        raise HTTPException(status_code=404, detail="report file not found") from exc


def parse_selection_outcome_csv(
    text: str,
    *,
    default_dataset_version: str | None = None,
    default_loop_type: str | None = None,
    default_source_type: str = "csv_import",
    default_privacy_level: str = "synthetic",
    default_synthetic: bool = True,
) -> list[dict[str, object]]:
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV file must include a header row")

    normalized_fieldnames = [_normalize_csv_field(field) for field in reader.fieldnames]
    if "case_id" not in normalized_fieldnames:
        raise ValueError("CSV file requires a case_id column")

    records: list[dict[str, object]] = []
    for row_number, row in enumerate(reader, start=2):
        normalized_row = {
            _normalize_csv_field(key): _clean_csv_value(value)
            for key, value in row.items()
            if key is not None
        }
        if not any(value for value in normalized_row.values()):
            continue
        if len(records) >= MAX_SELECTION_OUTCOME_CSV_ROWS:
            raise ValueError(
                f"CSV file exceeds max row count {MAX_SELECTION_OUTCOME_CSV_ROWS}"
            )

        case_id = normalized_row.get("case_id")
        if not case_id:
            raise ValueError(f"CSV row {row_number} requires case_id")

        record: dict[str, object] = {}
        metadata: dict[str, object] = {}
        for key, value in normalized_row.items():
            if value is None:
                continue
            if key.startswith("metadata."):
                metadata[key.removeprefix("metadata.")] = value
            elif key in SELECTION_OUTCOME_CSV_FIELDS:
                record[key] = value
            else:
                metadata[key] = value

        record.setdefault("dataset_version", default_dataset_version)
        record.setdefault("loop_type", default_loop_type)
        record.setdefault("source_type", default_source_type)
        record.setdefault("privacy_level", default_privacy_level)
        record.setdefault("synthetic", default_synthetic)
        if metadata:
            record["metadata"] = metadata
        records.append(record)

    if not records:
        raise ValueError("CSV file contains no outcome rows")
    return records


def build_selection_case_records_from_manifest(
    manifest_path: Path,
    manifest: dict[str, object],
    *,
    profile_id: str | None,
    limit: int | None,
    source_type: str,
    privacy_level: str,
    synthetic: bool,
) -> list[dict[str, object]]:
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise HTTPException(status_code=500, detail="dataset manifest cases must be a list")
    dataset_version = str(manifest.get("dataset_version") or "")
    manifest_dir = manifest_path.parent
    records: list[dict[str, object]] = []
    for item in cases[:limit] if limit is not None else cases:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id") or "")
        if not case_id:
            continue
        case_path = str(item.get("path") or "")
        prompt_path = str(item.get("prompt_path") or "")
        case_json = _read_manifest_relative_json(manifest_dir, case_path)
        prompt_text = _read_manifest_relative_text(manifest_dir, prompt_path)
        expected_output = (
            case_json.get("expected_output")
            if isinstance(case_json.get("expected_output"), dict)
            else {}
        )
        records.append(
            {
                "case_id": case_id,
                "profile_id": profile_id,
                "loop_type": item.get("loop_type"),
                "dataset_version": dataset_version or None,
                "case_path": case_path or None,
                "prompt_path": prompt_path or None,
                "prompt_text": prompt_text,
                "quality_passed": item.get("quality_passed"),
                "tags": item.get("tags") if isinstance(item.get("tags"), dict) else {},
                "expected_output": expected_output,
                "case": case_json,
                "source_type": source_type,
                "privacy_level": privacy_level,
                "synthetic": synthetic,
                "version": 1,
                "is_active": True,
            }
        )
    return records


def _read_manifest_relative_json(manifest_dir: Path, relative_path: str) -> dict[str, object]:
    if not relative_path:
        return {}
    path = (manifest_dir / relative_path).resolve()
    if manifest_dir.resolve() not in path.parents:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_manifest_relative_text(manifest_dir: Path, relative_path: str) -> str | None:
    if not relative_path:
        return None
    path = (manifest_dir / relative_path).resolve()
    if manifest_dir.resolve() not in path.parents:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def path_from_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def discover_eval_reports(root: Path) -> list[dict[str, object]]:
    if not root.exists():
        return []
    reports: list[dict[str, object]] = []
    for summary_path in root.glob("**/summary.json"):
        report_dir = summary_path.parent
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        reports.append(
            {
                "path": path_from_root(root, report_dir),
                "run_id": summary.get("run_id"),
                "dataset_version": summary.get("dataset_version"),
                "agent_id": summary.get("agent_id"),
                "api_base": summary.get("api_base"),
                "dry_run": summary.get("dry_run"),
                "case_count": summary.get("case_count"),
                "passed": summary.get("passed"),
                "failed": summary.get("failed"),
                "pass_rate": summary.get("pass_rate"),
                "created_at": summary.get("created_at"),
                "modified_at": summary_path.stat().st_mtime,
                "result_count": count_json_files(report_dir / "results"),
                "failed_case_count": count_json_files(report_dir / "failed_cases"),
            }
        )
    return sorted(reports, key=lambda item: float(item["modified_at"]), reverse=True)


def list_report_files(
    report_dir: Path,
    *,
    kind: Literal["results", "raw_outputs", "failed_cases"] | None = None,
) -> dict[str, list[dict[str, object]]] | list[dict[str, object]]:
    if kind:
        return list_json_files(report_dir, kind)
    files: dict[str, list[dict[str, object]]] = {
        "root": [],
        "results": list_json_files(report_dir, "results"),
        "raw_outputs": list_json_files(report_dir, "raw_outputs"),
        "failed_cases": list_json_files(report_dir, "failed_cases"),
    }
    for filename in ("summary.json", "eval_manifest.json"):
        path = report_dir / filename
        if path.is_file():
            files["root"].append(file_entry(report_dir, path))
    return files


def list_json_files(report_dir: Path, kind: str) -> list[dict[str, object]]:
    if kind not in REPORT_FILE_KINDS:
        raise HTTPException(status_code=400, detail="invalid report file kind")
    directory = report_dir / kind
    if not directory.exists():
        return []
    return [file_entry(report_dir, path) for path in sorted(directory.glob("*.json")) if path.is_file()]


def file_entry(report_dir: Path, path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "path": path_from_root(report_dir, path),
        "name": path.name,
        "size": stat.st_size,
        "modified_at": stat.st_mtime,
    }


def count_json_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob("*.json") if item.is_file())


def _normalize_csv_field(value: str | None) -> str:
    return (value or "").lstrip("\ufeff").strip().lower().replace(" ", "_").replace("-", "_")


def _clean_csv_value(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def resolve_eval_run_trace_task_id(db: Session, eval_run) -> int | None:
    summary = eval_run.summary_json if isinstance(eval_run.summary_json, dict) else {}
    trace_task_id = coerce_optional_int(summary.get("trace_task_id"))
    if trace_task_id is not None:
        return trace_task_id

    if not eval_run.background_job_id:
        return None
    job = (
        db.query(BackgroundJob)
        .filter(BackgroundJob.id == str(eval_run.background_job_id))
        .first()
    )
    if job is None or not isinstance(job.payload, dict):
        return None
    return coerce_optional_int(job.payload.get("trace_task_id"))


def serialize_trace_event(event: TraceEvent) -> dict[str, object]:
    data = redact_trace_data(event.data if isinstance(event.data, dict) else {})
    return {
        "id": int(event.id),
        "task_id": int(event.task_id),
        "build_id": event.build_id,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "loop_event_type": data.get("type") if isinstance(data, dict) else None,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "step_id": event.step_id,
        "parent_event_id": event.parent_event_id,
        "data": data,
    }


def redact_trace_data(value: object) -> object:
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            if key.lower() in TRACE_REDACT_KEYS:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_trace_data(item)
        return redacted
    if isinstance(value, list):
        return [redact_trace_data(item) for item in value]
    return value


def coerce_optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_failed_cases_archive(report_dir: Path) -> BytesIO:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in ("summary.json", "eval_manifest.json"):
            path = report_dir / filename
            if path.is_file():
                archive.write(path, arcname=filename)
        failed_dir = report_dir / "failed_cases"
        if failed_dir.exists():
            for path in sorted(failed_dir.glob("*.json")):
                if path.is_file():
                    archive.write(path, arcname=f"failed_cases/{path.name}")
    buffer.seek(0)
    return buffer


def _load_reuse_task_map(path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("reuse_task_map must be a JSON object")
    return {str(case_id): int(task_id) for case_id, task_id in data.items()}


def build_loop_eval_payload(
    *,
    request: LoopEvalRunRequest,
    dataset_manifest: Path,
    output_dir: Path,
    reuse_task_map: Path | None,
    selected_case_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "dataset_manifest": str(dataset_manifest),
        "output_dir": str(output_dir),
        "agent_id": request.agent_id,
        "dry_run": request.dry_run,
        "api_base": request.api_base,
        "api_key": request.api_key,
        "login_username": request.login_username,
        "login_password": request.login_password,
        "rotate_runtime_key": request.rotate_runtime_key,
        "reuse_task_map": _load_reuse_task_map(reuse_task_map)
        if reuse_task_map
        else None,
        "case_ids": selected_case_ids,
        "sampling": build_sampling_metadata(request, selected_case_ids),
        "selection_cases": build_selection_case_metadata(request, selected_case_ids),
        "limit": request.limit,
        "max_new_tasks": request.max_new_tasks,
        "stop_on_failure": request.stop_on_failure,
        "timeout_seconds": request.timeout_seconds,
        "poll_interval": request.poll_interval,
        "clean": request.clean,
    }


def build_sampling_metadata(
    request: LoopEvalRunRequest,
    selected_case_ids: list[str] | None,
) -> dict[str, object] | None:
    if not (request.sample_count or request.sample_loops or request.sample_tags):
        return None
    return {
        "sample_count": request.sample_count,
        "sample_seed": request.sample_seed,
        "sample_loops": request.sample_loops,
        "sample_tags": request.sample_tags,
        "selected_case_ids": selected_case_ids or [],
    }


def loop_eval_budget_scope(agent_id: int) -> str:
    return f"agent-{int(agent_id)}"


def build_selection_case_metadata(
    request: LoopEvalRunRequest,
    selected_case_ids: list[str] | None,
) -> dict[str, object] | None:
    if not (request.selection_case_ids or request.selection_profile_id):
        return None
    return {
        "selection_case_ids": request.selection_case_ids or [],
        "selection_profile_id": request.selection_profile_id,
        "active_only": request.selection_cases_active_only,
        "selected_case_ids": selected_case_ids or [],
    }


def resolve_loop_eval_case_ids(
    db: Session,
    *,
    user_id: int,
    request: LoopEvalRunRequest,
    dataset_manifest: Path,
) -> list[str] | None:
    selection_requested = bool(request.selection_case_ids or request.selection_profile_id)
    sampling_requested = bool(
        request.case_ids or request.sample_count or request.sample_loops or request.sample_tags
    )
    if request.selection_case_ids and request.selection_profile_id:
        raise HTTPException(
            status_code=400,
            detail="selection_case_ids cannot be combined with selection_profile_id",
        )
    if selection_requested and sampling_requested:
        raise HTTPException(
            status_code=400,
            detail=(
                "selection_case_ids/selection_profile_id cannot be combined with "
                "case_ids/sample_count/sample_loops/sample_tags"
            ),
        )
    if not selection_requested:
        return select_eval_case_ids(
            dataset_manifest,
            explicit_case_ids=request.case_ids,
            sample_count=request.sample_count,
            sample_seed=request.sample_seed,
            sample_loops=request.sample_loops,
            sample_tags=request.sample_tags,
        )

    selected = selection_loop_case_ids_for_eval(
        db,
        user_id=user_id,
        dataset_manifest=dataset_manifest,
        selection_case_ids=request.selection_case_ids,
        selection_profile_id=request.selection_profile_id,
        active_only=request.selection_cases_active_only,
    )
    if not selected:
        raise HTTPException(status_code=400, detail="selection case filters matched no cases")
    return selected


def selection_loop_case_ids_for_eval(
    db: Session,
    *,
    user_id: int,
    dataset_manifest: Path,
    selection_case_ids: list[str] | None = None,
    selection_profile_id: str | None = None,
    active_only: bool = True,
) -> list[str]:
    manifest_case_ids = load_manifest_case_ids(dataset_manifest)
    selected: list[dict[str, object]] = []
    if selection_case_ids:
        for selection_case_id in selection_case_ids:
            loop_case = get_selection_loop_case(
                db,
                user_id=user_id,
                loop_case_id=str(selection_case_id),
            )
            if loop_case is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"selection case not found: {selection_case_id}",
                )
            serialized = serialize_selection_loop_case(loop_case)
            if active_only and not bool(serialized.get("is_active")):
                continue
            selected.append(serialized)
    elif selection_profile_id:
        profile = get_selection_loop_profile(
            db,
            user_id=user_id,
            profile_id=selection_profile_id,
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="selection profile not found")
        _, selected = list_selection_loop_cases(
            db,
            user_id=user_id,
            limit=1000,
            offset=0,
            profile_id=selection_profile_id,
            is_active=True if active_only else None,
        )

    case_ids: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for loop_case in selected:
        case_id = str(loop_case.get("case_id") or "")
        if not case_id or case_id in seen:
            continue
        seen.add(case_id)
        if case_id not in manifest_case_ids:
            missing.append(case_id)
            continue
        case_ids.append(case_id)

    if missing:
        preview = ", ".join(missing[:5])
        suffix = "" if len(missing) <= 5 else f" and {len(missing) - 5} more"
        raise HTTPException(
            status_code=400,
            detail=f"selection cases are not present in dataset_manifest: {preview}{suffix}",
        )
    return case_ids


def select_eval_case_ids(
    dataset_manifest: Path,
    *,
    explicit_case_ids: list[str] | None,
    sample_count: int | None,
    sample_seed: int,
    sample_loops: list[str] | None,
    sample_tags: dict[str, str] | None,
) -> list[str] | None:
    if explicit_case_ids and (sample_count or sample_loops or sample_tags):
        raise HTTPException(
            status_code=400,
            detail="case_ids cannot be combined with sample_count/sample_loops/sample_tags",
        )
    if explicit_case_ids:
        return explicit_case_ids
    if not (sample_count or sample_loops or sample_tags):
        return None

    manifest = read_json_file(dataset_manifest)
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="dataset_manifest must be a JSON object")
    case_refs = manifest.get("cases")
    if not isinstance(case_refs, list):
        raise HTTPException(status_code=400, detail="dataset_manifest.cases must be a list")

    candidates: list[dict[str, object]] = []
    for case_ref in case_refs:
        if not isinstance(case_ref, dict):
            continue
        case_id = case_ref.get("case_id")
        loop_type = case_ref.get("loop_type")
        case_path = case_ref.get("path")
        if not isinstance(case_id, str) or not isinstance(loop_type, str) or not isinstance(case_path, str):
            continue
        if sample_loops and loop_type not in sample_loops:
            continue
        tags = load_case_tags(dataset_manifest.parent, case_path)
        if sample_tags and not tags_match(tags, sample_tags):
            continue
        candidates.append({"case_id": case_id, "loop_type": loop_type, "tags": tags})

    if not candidates:
        raise HTTPException(status_code=400, detail="sampling filters matched no cases")

    requested_count = sample_count or len(candidates)
    if requested_count > len(candidates):
        raise HTTPException(
            status_code=400,
            detail=f"sample_count={requested_count} exceeds matched case count={len(candidates)}",
        )

    return balanced_sample_case_ids(candidates, requested_count, seed=sample_seed)


def load_manifest_case_ids(dataset_manifest: Path) -> set[str]:
    manifest = read_json_file(dataset_manifest)
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="dataset_manifest must be a JSON object")
    case_refs = manifest.get("cases")
    if not isinstance(case_refs, list):
        raise HTTPException(status_code=400, detail="dataset_manifest.cases must be a list")
    case_ids: set[str] = set()
    for case_ref in case_refs:
        if isinstance(case_ref, dict) and case_ref.get("case_id"):
            case_ids.add(str(case_ref["case_id"]))
    return case_ids


def load_case_tags(dataset_root: Path, relative_path: str) -> dict[str, object]:
    case_path = (dataset_root / relative_path).resolve()
    resolved_root = dataset_root.resolve()
    if case_path != resolved_root and resolved_root not in case_path.parents:
        raise HTTPException(status_code=400, detail="case path must stay under dataset root")
    data = read_json_file(case_path)
    if not isinstance(data, dict):
        return {}
    tags = data.get("tags")
    return tags if isinstance(tags, dict) else {}


def tags_match(tags: dict[str, object], expected: dict[str, str]) -> bool:
    for key, value in expected.items():
        if str(tags.get(key)) != value:
            return False
    return True


def estimate_new_task_count(
    dataset_manifest: Path,
    *,
    selected_case_ids: list[str] | None,
    limit: int | None,
    reuse_task_map: object,
    dry_run: bool,
) -> int:
    if dry_run:
        return 0
    manifest = read_json_file(dataset_manifest)
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="dataset_manifest must be a JSON object")
    case_refs = manifest.get("cases")
    if not isinstance(case_refs, list):
        raise HTTPException(status_code=400, detail="dataset_manifest.cases must be a list")

    selected = case_refs
    if selected_case_ids:
        selected_set = set(selected_case_ids)
        selected = [
            case_ref
            for case_ref in case_refs
            if isinstance(case_ref, dict) and case_ref.get("case_id") in selected_set
        ]
    if limit is not None:
        selected = selected[:limit]

    reuse_ids: set[str] = set()
    if isinstance(reuse_task_map, dict):
        reuse_ids = {str(case_id) for case_id in reuse_task_map}
    return sum(
        1
        for case_ref in selected
        if isinstance(case_ref, dict) and str(case_ref.get("case_id")) not in reuse_ids
    )


def balanced_sample_case_ids(
    cases: list[dict[str, object]],
    sample_count: int,
    *,
    seed: int,
) -> list[str]:
    by_loop: dict[str, list[dict[str, object]]] = {}
    for case in cases:
        by_loop.setdefault(str(case["loop_type"]), []).append(case)

    rng = random.Random(seed)
    for bucket in by_loop.values():
        bucket.sort(key=lambda item: str(item["case_id"]))
        rng.shuffle(bucket)

    selected: list[dict[str, object]] = []
    loop_order = sorted(by_loop)
    while len(selected) < sample_count:
        progressed = False
        for loop in loop_order:
            bucket = by_loop[loop]
            if bucket and len(selected) < sample_count:
                selected.append(bucket.pop(0))
                progressed = True
        if not progressed:
            break

    selected.sort(key=lambda item: (str(item["loop_type"]), str(item["case_id"])))
    return [str(item["case_id"]) for item in selected]


def default_worker_api_base(api_base: str) -> str | None:
    normalized = api_base.rstrip("/")
    if normalized in {"http://localhost", "https://localhost"}:
        return "http://nginx"
    return None


def discover_dataset_manifests(root: Path, *, limit: int = 20) -> list[dict[str, object]]:
    if not root.exists():
        return []
    manifests = sorted(
        root.glob("**/dataset_manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    results: list[dict[str, object]] = []
    for path in manifests[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        results.append(
            {
                "path": str(path),
                "dataset_version": data.get("dataset_version"),
                "level": data.get("level"),
                "case_count": data.get("case_count"),
                "loops": data.get("loops"),
                "modified_at": path.stat().st_mtime,
            }
        )
    return results
