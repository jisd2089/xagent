"""Shared constants and lightweight helpers for loop data generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


LOOP1_DIR = "loop1_candidate_cases"
LOOP2_DIR = "loop2_feedback_cases"
LOOP3_DIR = "loop3_outcome_cases"
PROMPT_DIR = "regression_prompts"
COVERAGE_DIR = "coverage_reports"


LEVEL_COUNTS: dict[str, dict[str, int]] = {
    "smoke": {"loop1": 6, "loop2": 3, "loop3": 3},
    "mvp": {"loop1": 30, "loop2": 15, "loop3": 15},
    "regression": {"loop1": 120, "loop2": 60, "loop3": 60},
    "production_eval": {"loop1": 300, "loop2": 120, "loop3": 120},
}


LOOP_DIRS = {
    "loop1": LOOP1_DIR,
    "loop2": LOOP2_DIR,
    "loop3": LOOP3_DIR,
}


@dataclass(frozen=True)
class ValidationIssue:
    """One data quality issue."""

    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Quality-gate result for one generated case."""

    passed: bool
    issues: tuple[ValidationIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [
                {"code": issue.code, "message": issue.message}
                for issue in self.issues
            ],
        }


def utc_version_stamp() -> str:
    """Return a stable date-based dataset version stamp."""

    # Keep the version deterministic enough for local regeneration while still
    # distinguishing implementation generations.
    return "2026-07-02.auto.001"

