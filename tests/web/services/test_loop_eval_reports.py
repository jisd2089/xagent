from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from xagent.web import models as _models  # noqa: F401
from xagent.web.api.loop_data import selection_loop_case_ids_for_eval
from xagent.web.models.database import Base
from xagent.web.models.loop_eval import (
    SelectionEvalResult,
    SelectionEvalRun,
    SelectionLoopCase,
    SelectionLoopProfile,
    SelectionOutcome,
)
from xagent.web.services.loop_eval_reports import (
    create_selection_loop_profile,
    delete_selection_loop_case,
    delete_selection_loop_profile,
    get_selection_loop_case,
    get_selection_loop_profile,
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
    update_selection_loop_case,
    update_selection_loop_profile,
)


def test_persist_loop_eval_report_upserts_run_and_results(tmp_path) -> None:
    db = _session()
    eval_dir = tmp_path / "eval_reports" / "run_a"
    (eval_dir / "results").mkdir(parents=True)
    (eval_dir / "raw_outputs").mkdir()
    _write_json(
        eval_dir / "results" / "case_a.json",
        {
            "case_id": "case_a",
            "loop_type": "loop1",
            "dataset_version": "dataset",
            "transport": {"mode": "http_reuse", "task_id": 203},
            "judge": {"passed": True, "score": 1.0},
            "passed": True,
            "tags": {"job_family": "backend_architect"},
        },
    )
    _write_json(eval_dir / "raw_outputs" / "case_a.json", {"output": "ok"})
    summary = {
        "run_id": "dataset.agent31",
        "dataset_version": "dataset",
        "agent_id": 31,
        "api_base": "http://localhost",
        "worker_api_base": "http://nginx",
        "dry_run": False,
        "case_count": 1,
        "passed": 1,
        "failed": 0,
        "pass_rate": 1.0,
        "by_loop": {"loop1": {"total": 1, "passed": 1}},
        "budget": {"new_task_count": 0},
        "created_at": "2026-07-02T10:00:00+00:00",
    }

    eval_run = persist_loop_eval_report(
        db,
        user_id=1,
        background_job_id="job-a",
        eval_dir=eval_dir,
        summary=summary,
    )

    assert db.query(SelectionEvalRun).count() == 1
    assert db.query(SelectionEvalResult).count() == 1
    assert eval_run.summary_json["eval_run_id"] == eval_run.id
    result = db.query(SelectionEvalResult).one()
    assert result.case_id == "case_a"
    assert result.task_id == 203
    assert result.raw_output_path == "raw_outputs/case_a.json"

    _write_json(
        eval_dir / "results" / "case_a.json",
        {
            "case_id": "case_a",
            "loop_type": "loop1",
            "dataset_version": "dataset",
            "transport": {"mode": "http_reuse", "task_id": 203},
            "judge": {"passed": False, "score": 0.0},
            "passed": False,
        },
    )
    persist_loop_eval_report(db, user_id=1, eval_dir=eval_dir, summary={**summary, "failed": 1})

    assert db.query(SelectionEvalRun).count() == 1
    assert db.query(SelectionEvalResult).count() == 1
    _, runs = list_loop_eval_runs(db, user_id=1, limit=10, offset=0)
    _, results = list_loop_eval_results(db, eval_run_id=eval_run.id, limit=10, offset=0)
    assert runs[0]["failed"] == 1
    assert results[0]["passed"] is False


def test_get_loop_eval_metrics_groups_runs_and_results(tmp_path) -> None:
    db = _session()
    _persist_report(
        db,
        tmp_path,
        name="run_a",
        dataset_version="dataset_a",
        dry_run=True,
        results=[
            ("case_a", "loop1", True),
            ("case_b", "loop2", False),
        ],
    )
    _persist_report(
        db,
        tmp_path,
        name="run_b",
        dataset_version="dataset_b",
        dry_run=False,
        results=[
            ("case_c", "loop1", True),
        ],
    )

    metrics = get_loop_eval_metrics(db, user_id=1, recent_limit=5)

    assert metrics["totals"] == {
        "run_count": 2,
        "case_count": 3,
        "result_count": 3,
        "passed": 2,
        "failed": 1,
        "pass_rate": 2 / 3,
    }
    assert metrics["by_loop"] == [
        {
            "loop_type": "loop1",
            "result_count": 2,
            "passed": 2,
            "failed": 0,
            "pass_rate": 1.0,
        },
        {
            "loop_type": "loop2",
            "result_count": 1,
            "passed": 0,
            "failed": 1,
            "pass_rate": 0.0,
        },
    ]
    assert {item["key"]: item["case_count"] for item in metrics["by_dataset"]} == {
        "dataset_a": 2,
        "dataset_b": 1,
    }

    dry_run_metrics = get_loop_eval_metrics(db, user_id=1, dry_run=True)

    assert dry_run_metrics["totals"]["run_count"] == 1
    assert dry_run_metrics["totals"]["case_count"] == 2
    assert dry_run_metrics["totals"]["failed"] == 1


def test_import_selection_outcomes_upserts_and_metrics() -> None:
    db = _session()
    first = import_selection_outcomes(
        db,
        user_id=1,
        import_batch_id="batch-a",
        records=[
            {
                "case_id": "case_a",
                "dataset_version": "dataset",
                "loop_type": "loop3",
                "agent_recommendation": "hire",
                "actual_outcome": "successful",
                "hired": True,
                "performance_rating": 4.2,
                "privacy_level": "synthetic",
                "synthetic": True,
            },
            {
                "case_id": "case_b",
                "dataset_version": "dataset",
                "loop_type": "loop3",
                "agent_recommendation": "hire",
                "actual_outcome": "unsuccessful",
                "hired": True,
                "performance_rating": 2.0,
            },
            {
                "case_id": "case_c",
                "dataset_version": "dataset",
                "loop_type": "loop1",
                "agent_recommendation": "no_hire",
                "actual_outcome": "successful",
            },
        ],
    )

    assert first["imported_count"] == 3
    assert db.query(SelectionOutcome).count() == 3

    import_selection_outcomes(
        db,
        user_id=1,
        import_batch_id="batch-b",
        records=[
            {
                "case_id": "case_b",
                "dataset_version": "dataset",
                "loop_type": "loop3",
                "agent_recommendation": "no_hire",
                "actual_outcome": "unsuccessful",
            },
        ],
    )

    assert db.query(SelectionOutcome).count() == 3
    _, outcomes = list_selection_outcomes(
        db,
        user_id=1,
        limit=10,
        offset=0,
        dataset_version="dataset",
    )
    assert {item["case_id"] for item in outcomes} == {"case_a", "case_b", "case_c"}

    metrics = get_selection_outcome_metrics(db, user_id=1, dataset_version="dataset")

    assert metrics["outcome_count"] == 3
    assert metrics["confusion"] == {
        "evaluated": 3,
        "skipped": 0,
        "true_positive": 1,
        "true_negative": 1,
        "false_positive": 0,
        "false_negative": 1,
        "false_positive_rate": 0.0,
        "false_negative_rate": 0.5,
        "precision": 1.0,
        "recall": 0.5,
    }


def test_selection_loop_profile_crud() -> None:
    db = _session()

    profile = create_selection_loop_profile(
        db,
        user_id=1,
        data={
            "name": "backend architect interview loop",
            "job_family": "backend_architect",
            "job_title": "Backend Architect",
            "level": "senior",
            "locale": "zh-CN",
            "profile": {
                "competencies": ["system_design", "technical_leadership"],
                "loop_weights": {"loop1": 0.4, "loop2": 0.3, "loop3": 0.3},
            },
            "source_type": "test",
            "privacy_level": "synthetic",
            "synthetic": True,
            "version": 1,
        },
    )

    assert db.query(SelectionLoopProfile).count() == 1
    assert profile.job_family == "backend_architect"
    assert profile.profile_json["loop_weights"]["loop1"] == 0.4

    total, profiles = list_selection_loop_profiles(
        db,
        user_id=1,
        limit=10,
        offset=0,
        job_family="backend_architect",
        is_active=True,
    )
    assert total == 1
    assert profiles[0]["name"] == "backend architect interview loop"

    loaded = get_selection_loop_profile(db, user_id=1, profile_id=profile.id)
    assert loaded is not None
    update_selection_loop_profile(
        db,
        profile=loaded,
        data={
            "level": "principal",
            "profile": {"competencies": ["architecture_review"]},
            "is_active": False,
        },
    )

    updated = get_selection_loop_profile(db, user_id=1, profile_id=profile.id)
    assert updated is not None
    assert updated.level == "principal"
    assert updated.is_active is False
    assert updated.profile_json == {"competencies": ["architecture_review"]}

    delete_selection_loop_profile(db, profile=updated)
    assert db.query(SelectionLoopProfile).count() == 0


def test_selection_loop_case_import_upsert_and_crud() -> None:
    db = _session()
    imported = import_selection_loop_cases(
        db,
        user_id=1,
        records=[
            {
                "case_id": "loop1_backend_architect_001",
                "loop_type": "loop1",
                "dataset_version": "dataset",
                "case_path": "loop1/loop1_backend_architect_001.json",
                "prompt_path": "prompts/loop1_backend_architect_001.md",
                "prompt_text": "Audit the candidate evidence.",
                "quality_passed": True,
                "tags": {"job_family": "backend_architect"},
                "expected_output": {"must_include": ["claim_risk"]},
                "case": {"case_id": "loop1_backend_architect_001"},
                "source_type": "test",
            },
        ],
    )

    assert imported["imported_count"] == 1
    assert db.query(SelectionLoopCase).count() == 1
    loop_case = db.query(SelectionLoopCase).one()
    assert loop_case.tags == {"job_family": "backend_architect"}

    import_selection_loop_cases(
        db,
        user_id=1,
        records=[
            {
                "case_id": "loop1_backend_architect_001",
                "loop_type": "loop1",
                "dataset_version": "dataset",
                "quality_passed": False,
                "tags": {"job_family": "backend_architect", "difficulty": "hard"},
                "case": {"case_id": "loop1_backend_architect_001", "updated": True},
            },
        ],
    )

    assert db.query(SelectionLoopCase).count() == 1
    total, cases = list_selection_loop_cases(
        db,
        user_id=1,
        limit=10,
        offset=0,
        dataset_version="dataset",
        loop_type="loop1",
    )
    assert total == 1
    assert cases[0]["quality_passed"] is False
    assert cases[0]["tags"]["difficulty"] == "hard"

    loaded = get_selection_loop_case(db, user_id=1, loop_case_id=loop_case.id)
    assert loaded is not None
    update_selection_loop_case(
        db,
        loop_case=loaded,
        data={"is_active": False, "expected_output": {"must_include": ["BARS"]}},
    )
    updated = get_selection_loop_case(db, user_id=1, loop_case_id=loop_case.id)
    assert updated is not None
    assert updated.is_active is False
    assert updated.expected_output == {"must_include": ["BARS"]}

    delete_selection_loop_case(db, loop_case=updated)
    assert db.query(SelectionLoopCase).count() == 0


def test_selection_loop_case_ids_for_eval_uses_profile_cases(tmp_path) -> None:
    db = _session()
    profile = create_selection_loop_profile(
        db,
        user_id=1,
        data={"name": "backend profile", "job_family": "backend_architect"},
    )
    import_selection_loop_cases(
        db,
        user_id=1,
        records=[
            {
                "profile_id": profile.id,
                "case_id": "case_a",
                "loop_type": "loop1",
                "dataset_version": "dataset",
                "is_active": True,
            },
            {
                "profile_id": profile.id,
                "case_id": "case_b",
                "loop_type": "loop2",
                "dataset_version": "dataset",
                "is_active": True,
            },
        ],
    )
    manifest = tmp_path / "dataset_manifest.json"
    _write_json(
        manifest,
        {
            "cases": [
                {"case_id": "case_a", "loop_type": "loop1"},
                {"case_id": "case_b", "loop_type": "loop2"},
            ]
        },
    )

    selected = selection_loop_case_ids_for_eval(
        db,
        user_id=1,
        dataset_manifest=manifest,
        selection_profile_id=profile.id,
    )

    assert selected == ["case_a", "case_b"]


def test_selection_loop_case_ids_for_eval_rejects_manifest_mismatch(tmp_path) -> None:
    db = _session()
    imported = import_selection_loop_cases(
        db,
        user_id=1,
        records=[
            {
                "case_id": "case_not_in_manifest",
                "loop_type": "loop1",
                "dataset_version": "dataset",
            },
        ],
    )
    manifest = tmp_path / "dataset_manifest.json"
    _write_json(manifest, {"cases": [{"case_id": "case_a", "loop_type": "loop1"}]})

    with pytest.raises(HTTPException) as exc_info:
        selection_loop_case_ids_for_eval(
            db,
            user_id=1,
            dataset_manifest=manifest,
            selection_case_ids=[imported["cases"][0]["id"]],
        )

    assert exc_info.value.status_code == 400
    assert "not present in dataset_manifest" in str(exc_info.value.detail)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _persist_report(
    db,
    tmp_path,
    *,
    name: str,
    dataset_version: str,
    dry_run: bool,
    results: list[tuple[str, str, bool]],
) -> None:
    eval_dir = tmp_path / "eval_reports" / name
    (eval_dir / "results").mkdir(parents=True)
    passed = 0
    for case_id, loop_type, is_passed in results:
        passed += 1 if is_passed else 0
        _write_json(
            eval_dir / "results" / f"{case_id}.json",
            {
                "case_id": case_id,
                "loop_type": loop_type,
                "dataset_version": dataset_version,
                "judge": {"passed": is_passed, "score": 1.0 if is_passed else 0.0},
                "passed": is_passed,
            },
        )
    persist_loop_eval_report(
        db,
        user_id=1,
        eval_dir=eval_dir,
        summary={
            "run_id": f"{dataset_version}.agent31",
            "dataset_version": dataset_version,
            "agent_id": 31,
            "api_base": "http://localhost",
            "dry_run": dry_run,
            "case_count": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": passed / len(results),
        },
    )


def _write_json(path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")
