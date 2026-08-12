from __future__ import annotations

import json
import zipfile

import pytest
from fastapi import HTTPException

from xagent.web.api.loop_data import (
    LoopDataGenerateRequest,
    build_loop_data_generate_payload,
    build_failed_cases_archive,
    discover_eval_reports,
    estimate_new_task_count,
    list_report_files,
    parse_selection_outcome_csv,
    read_json_file,
    resolve_optional_loop_dir,
    resolve_loop_report_dir,
    resolve_loop_report_file,
    run_loop_data_generation_payload,
    select_eval_case_ids,
)


def test_discover_eval_reports_returns_summary_and_counts(tmp_path) -> None:
    report_dir = tmp_path / "eval_reports" / "run_a"
    (report_dir / "results").mkdir(parents=True)
    (report_dir / "failed_cases").mkdir()
    _write_json(
        report_dir / "summary.json",
        {
            "run_id": "dataset.agent31",
            "dataset_version": "dataset",
            "agent_id": 31,
            "api_base": "http://localhost",
            "dry_run": False,
            "case_count": 2,
            "passed": 1,
            "failed": 1,
            "pass_rate": 0.5,
        },
    )
    _write_json(report_dir / "results" / "case_a.json", {"passed": True})
    _write_json(report_dir / "failed_cases" / "case_b.json", {"passed": False})

    reports = discover_eval_reports(tmp_path)

    assert reports == [
        {
            "path": "eval_reports/run_a",
            "run_id": "dataset.agent31",
            "dataset_version": "dataset",
            "agent_id": 31,
            "api_base": "http://localhost",
            "dry_run": False,
            "case_count": 2,
            "passed": 1,
            "failed": 1,
            "pass_rate": 0.5,
            "created_at": None,
            "modified_at": reports[0]["modified_at"],
            "result_count": 1,
            "failed_case_count": 1,
        }
    ]


def test_report_file_resolution_rejects_path_escape(tmp_path) -> None:
    report_dir = tmp_path / "run"
    report_dir.mkdir()
    _write_json(report_dir / "summary.json", {})
    outside = tmp_path / "outside.json"
    _write_json(outside, {})

    resolved = resolve_loop_report_dir(tmp_path, "run")
    with pytest.raises(HTTPException) as exc_info:
        resolve_loop_report_file(resolved, "../outside.json")

    assert exc_info.value.status_code == 400


def test_list_report_files_and_read_json(tmp_path) -> None:
    report_dir = tmp_path / "run"
    (report_dir / "results").mkdir(parents=True)
    _write_json(report_dir / "summary.json", {"passed": 1})
    _write_json(report_dir / "results" / "case_a.json", {"case_id": "case_a"})

    files = list_report_files(report_dir)

    assert files["root"][0]["path"] == "summary.json"
    assert files["results"][0]["path"] == "results/case_a.json"
    assert read_json_file(report_dir / "results" / "case_a.json") == {
        "case_id": "case_a"
    }


def test_build_failed_cases_archive_contains_summary_manifest_and_failed_cases(tmp_path) -> None:
    report_dir = tmp_path / "run"
    (report_dir / "failed_cases").mkdir(parents=True)
    _write_json(report_dir / "summary.json", {"failed": 1})
    _write_json(report_dir / "eval_manifest.json", {"result_files": []})
    _write_json(report_dir / "failed_cases" / "case_a.json", {"case_id": "case_a"})

    archive = build_failed_cases_archive(report_dir)

    with zipfile.ZipFile(archive) as zip_file:
        assert sorted(zip_file.namelist()) == [
            "eval_manifest.json",
            "failed_cases/case_a.json",
            "summary.json",
        ]


def test_select_eval_case_ids_balances_across_loops(tmp_path) -> None:
    manifest = _write_dataset(tmp_path)

    selected = select_eval_case_ids(
        manifest,
        explicit_case_ids=None,
        sample_count=3,
        sample_seed=7,
        sample_loops=None,
        sample_tags=None,
    )

    assert len(selected) == 3
    assert {case_id.split("_", 1)[0] for case_id in selected} == {
        "loop1",
        "loop2",
        "loop3",
    }


def test_select_eval_case_ids_filters_by_loop_and_tags(tmp_path) -> None:
    manifest = _write_dataset(tmp_path)

    selected = select_eval_case_ids(
        manifest,
        explicit_case_ids=None,
        sample_count=1,
        sample_seed=7,
        sample_loops=["loop1"],
        sample_tags={"job_family": "backend_architect"},
    )

    assert selected == ["loop1_backend_architect_002"]


def test_select_eval_case_ids_rejects_explicit_ids_with_sampling(tmp_path) -> None:
    manifest = _write_dataset(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        select_eval_case_ids(
            manifest,
            explicit_case_ids=["loop1_industrial_ai_support_001"],
            sample_count=1,
            sample_seed=7,
            sample_loops=None,
            sample_tags=None,
        )

    assert exc_info.value.status_code == 400


def test_estimate_new_task_count_honors_limit_and_reuse_map(tmp_path) -> None:
    manifest = _write_dataset(tmp_path)

    assert (
        estimate_new_task_count(
            manifest,
            selected_case_ids=None,
            limit=4,
            reuse_task_map=None,
            dry_run=False,
        )
        == 4
    )
    assert (
        estimate_new_task_count(
            manifest,
            selected_case_ids=[
                "loop1_industrial_ai_support_001",
                "loop1_backend_architect_002",
            ],
            limit=None,
            reuse_task_map={"loop1_backend_architect_002": 203},
            dry_run=False,
        )
        == 1
    )
    assert (
        estimate_new_task_count(
            manifest,
            selected_case_ids=None,
            limit=None,
            reuse_task_map=None,
            dry_run=True,
        )
        == 0
    )


def test_parse_selection_outcome_csv_applies_defaults_and_metadata() -> None:
    records = parse_selection_outcome_csv(
        "\ufeffcase_id,agent recommendation,actual-outcome,performance_rating,metadata.approval_id,reviewer\n"
        "case_a,Hire,Successful,4.2,approval-1,auditor-a\n",
        default_dataset_version="dataset",
        default_loop_type="loop3",
        default_source_type="csv_verify",
        default_privacy_level="internal",
        default_synthetic=False,
    )

    assert records == [
        {
            "case_id": "case_a",
            "agent_recommendation": "Hire",
            "actual_outcome": "Successful",
            "performance_rating": "4.2",
            "dataset_version": "dataset",
            "loop_type": "loop3",
            "source_type": "csv_verify",
            "privacy_level": "internal",
            "synthetic": False,
            "metadata": {
                "approval_id": "approval-1",
                "reviewer": "auditor-a",
            },
        }
    ]


def test_parse_selection_outcome_csv_requires_case_id_header() -> None:
    with pytest.raises(ValueError, match="case_id"):
        parse_selection_outcome_csv("actual_outcome\nsuccessful\n")


def test_loop_data_generation_payload_supports_seed_and_adversarial(tmp_path) -> None:
    seed_dir = tmp_path / "seeds"
    seed_dir.mkdir()
    (seed_dir / "candidate.txt").write_text(
        "Name: Candidate\nphone: 13812345678\nI led reliability work and improved latency 60%.\n",
        encoding="utf-8",
    )
    request = LoopDataGenerateRequest(
        level="smoke",
        loops=["loop1"],
        output_subdir="generated",
        seed_subdir="seeds",
        adversarial_copies=1,
    )
    payload = build_loop_data_generate_payload(
        request=request,
        output_dir=tmp_path / "generated",
        seed_dir=seed_dir,
        trace_task_id=123,
    )

    result = run_loop_data_generation_payload(payload)

    assert result["case_count"] == 12
    assert result["local_seed_summary"]["seed_count"] == 1
    assert result["local_seed_summary"]["pii_removed"]["phone"] == 1
    assert result["adversarial"] == {"copies_per_case": 1, "case_count": 6}
    assert result["mutation_plan"] == []
    manifest = read_json_file(tmp_path / "generated" / "dataset_manifest.json")
    assert isinstance(manifest, dict)
    assert sum(1 for item in manifest["cases"] if item.get("adversarial")) == 6


def test_resolve_optional_loop_dir_rejects_escape(tmp_path) -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_optional_loop_dir(tmp_path / "root", "../outside")

    assert exc_info.value.status_code == 400


def _write_json(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_dataset(tmp_path):
    cases = [
        ("loop1_industrial_ai_support_001", "loop1", "industrial_ai_support"),
        ("loop1_backend_architect_002", "loop1", "backend_architect"),
        ("loop2_industrial_ai_support_001", "loop2", "industrial_ai_support"),
        ("loop2_backend_architect_002", "loop2", "backend_architect"),
        ("loop3_industrial_ai_support_001", "loop3", "industrial_ai_support"),
        ("loop3_backend_architect_002", "loop3", "backend_architect"),
    ]
    manifest_cases = []
    for case_id, loop_type, job_family in cases:
        case_path = f"cases/{case_id}.json"
        _write_json(
            tmp_path / case_path,
            {
                "case_id": case_id,
                "loop_type": loop_type,
                "tags": {"job_family": job_family},
            },
        )
        manifest_cases.append(
            {"case_id": case_id, "loop_type": loop_type, "path": case_path}
        )
    manifest = tmp_path / "dataset_manifest.json"
    _write_json(manifest, {"cases": manifest_cases})
    return manifest
