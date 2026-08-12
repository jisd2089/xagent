"""Quality gates and coverage reporting for generated loop data."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from scripts.loop_data_factory.models import ValidationIssue, ValidationResult


PHONE_RE = re.compile(r"(?<!\d)(?:1[3-9]\d{9})(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")


def validate_loop_case(case: dict[str, Any]) -> ValidationResult:
    issues: list[ValidationIssue] = []
    _require(case, "case_id", issues)
    _require(case, "loop_type", issues)
    _require(case, "source_type", issues)
    _require(case, "synthetic", issues)
    _require(case, "privacy_level", issues)
    _require(case, "tags", issues)
    _require(case, "input", issues)
    _require(case, "expected_output", issues)

    if case.get("source_type") == "synthetic_case" and case.get("synthetic") is not True:
        issues.append(
            ValidationIssue("synthetic_flag", "synthetic_case must set synthetic=true")
        )

    serialized = repr(case)
    if PHONE_RE.search(serialized):
        issues.append(ValidationIssue("pii_phone", "case contains phone-like PII"))
    if EMAIL_RE.search(serialized):
        issues.append(ValidationIssue("pii_email", "case contains email-like PII"))
    if ID_CARD_RE.search(serialized):
        issues.append(ValidationIssue("pii_id_card", "case contains ID-card-like PII"))

    loop_type = case.get("loop_type")
    if loop_type == "loop1":
        _validate_loop1(case, issues)
    elif loop_type == "loop2":
        _validate_loop2(case, issues)
    elif loop_type == "loop3":
        _validate_loop3(case, issues)
    else:
        issues.append(ValidationIssue("loop_type", f"unsupported loop type {loop_type!r}"))

    return ValidationResult(passed=not issues, issues=tuple(issues))


def apply_quality(case: dict[str, Any]) -> dict[str, Any]:
    result = validate_loop_case(case)
    updated = dict(case)
    updated["quality"] = result.to_dict()
    return updated


def build_coverage_report(cases: list[dict[str, Any]], dataset_version: str) -> dict[str, Any]:
    by_loop: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        by_loop[case.get("loop_type", "unknown")].append(case)

    report: dict[str, Any] = {
        "dataset_version": dataset_version,
        "case_count": {loop: len(items) for loop, items in sorted(by_loop.items())},
        "loops": {},
        "gaps": [],
    }
    for loop in ("loop1", "loop2", "loop3"):
        items = by_loop.get(loop, [])
        report["loops"][loop] = _loop_coverage(loop, items)
        report["gaps"].extend(_loop_gaps(loop, report["loops"][loop]))
    total = len(cases)
    passed = sum(1 for case in cases if case.get("quality", {}).get("passed"))
    report["quality_pass_rate"] = round(passed / total, 4) if total else 0.0
    return report


def _validate_loop1(case: dict[str, Any], issues: list[ValidationIssue]) -> None:
    input_data = case.get("input", {})
    expected = case.get("expected_output", {})
    if not input_data.get("job_description"):
        issues.append(ValidationIssue("loop1_job", "Loop 1 requires job_description"))
    if not input_data.get("candidate_profile"):
        issues.append(ValidationIssue("loop1_candidate", "Loop 1 requires candidate_profile"))
    if not input_data.get("candidate_claims"):
        issues.append(ValidationIssue("loop1_claim", "Loop 1 requires at least one claim"))
    if not expected.get("claim_risks"):
        issues.append(ValidationIssue("loop1_expected", "Loop 1 requires expected claim risks"))
    if not expected.get("bars_dimensions"):
        issues.append(ValidationIssue("loop1_bars", "Loop 1 requires BARS dimensions"))


def _validate_loop2(case: dict[str, Any], issues: list[ValidationIssue]) -> None:
    input_data = case.get("input", {})
    expected = case.get("expected_output", {})
    if not input_data.get("selection_loop_profile"):
        issues.append(ValidationIssue("loop2_profile", "Loop 2 requires profile"))
    if not input_data.get("stakeholder_feedback"):
        issues.append(ValidationIssue("loop2_feedback", "Loop 2 requires feedback"))
    weights = expected.get("expected_weight_update", {})
    if not weights:
        issues.append(ValidationIssue("loop2_weights", "Loop 2 requires expected weights"))
    elif abs(sum(weights.values()) - 1.0) > 0.02:
        issues.append(
            ValidationIssue("loop2_weight_sum", "expected weights must sum to 1.0")
        )
    if "sensitive_attribute_questions" not in expected.get("expected_probe_update", {}).get(
        "remove", []
    ):
        issues.append(
            ValidationIssue(
                "loop2_compliance",
                "Loop 2 expected probe update must remove sensitive questions",
            )
        )


def _validate_loop3(case: dict[str, Any], issues: list[ValidationIssue]) -> None:
    input_data = case.get("input", {})
    expected = case.get("expected_output", {})
    if not input_data.get("batch_summary"):
        issues.append(ValidationIssue("loop3_batch", "Loop 3 requires batch summary"))
    if not input_data.get("candidate_outcomes"):
        issues.append(ValidationIssue("loop3_outcomes", "Loop 3 requires outcomes"))
    if "calibration_expected" not in expected:
        issues.append(
            ValidationIssue("loop3_calibration", "Loop 3 requires expected calibration")
        )
    batch = input_data.get("batch_summary", {})
    candidate_count = int(batch.get("candidate_count", 0) or 0)
    if candidate_count < 10 and not expected.get("sample_size_warning"):
        issues.append(
            ValidationIssue(
                "loop3_sample_warning",
                "small Loop 3 samples require a sample-size warning",
            )
        )


def _require(case: dict[str, Any], key: str, issues: list[ValidationIssue]) -> None:
    if key not in case:
        issues.append(ValidationIssue("required_field", f"missing field {key}"))


def _loop_coverage(loop: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    tag_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for case in items:
        for key, value in case.get("tags", {}).items():
            tag_counts[key][str(value)] += 1
    return {
        "cases": len(items),
        "quality_pass_rate": _pass_rate(items),
        "tags": {
            key: dict(sorted(counter.items()))
            for key, counter in sorted(tag_counts.items())
        },
    }


def _pass_rate(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    passed = sum(1 for item in items if item.get("quality", {}).get("passed"))
    return round(passed / len(items), 4)


def _loop_gaps(loop: str, coverage: dict[str, Any]) -> list[str]:
    if coverage["cases"] == 0:
        return [f"{loop}: no cases generated"]
    gaps: list[str] = []
    required_tags = {
        "loop1": ["job_family", "claim_risk", "bias_type", "compliance_risk"],
        "loop2": ["feedback_source", "feedback_type", "conflict_type"],
        "loop3": ["outcome_type", "miss_type", "sample_size_band"],
    }[loop]
    tags = coverage.get("tags", {})
    for tag in required_tags:
        if not tags.get(tag):
            gaps.append(f"{loop}: missing coverage tag {tag}")
    if coverage.get("quality_pass_rate", 0.0) < 0.9:
        gaps.append(f"{loop}: quality pass rate below 0.9")
    return gaps

