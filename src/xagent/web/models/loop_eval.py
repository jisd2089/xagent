from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class SelectionLoopProfile(Base):  # type: ignore
    __tablename__ = "selection_loop_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False, index=True)
    job_family = Column(String(128), nullable=True, index=True)
    job_title = Column(String(255), nullable=True, index=True)
    level = Column(String(64), nullable=True, index=True)
    locale = Column(String(64), nullable=True)
    profile_json = Column(JSON, nullable=False, default=dict)
    source_type = Column(String(64), nullable=False, default="manual", index=True)
    privacy_level = Column(String(64), nullable=False, default="synthetic", index=True)
    synthetic = Column(Boolean, nullable=False, default=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SelectionLoopCase(Base):  # type: ignore
    __tablename__ = "selection_loop_cases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    profile_id = Column(
        String(36),
        ForeignKey("selection_loop_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    case_id = Column(String(255), nullable=False, index=True)
    loop_type = Column(String(32), nullable=True, index=True)
    dataset_version = Column(String(255), nullable=True, index=True)
    case_path = Column(Text, nullable=True)
    prompt_path = Column(Text, nullable=True)
    prompt_text = Column(Text, nullable=True)
    quality_passed = Column(Boolean, nullable=True, index=True)
    tags = Column(JSON, nullable=True)
    expected_output = Column(JSON, nullable=True)
    case_json = Column(JSON, nullable=False, default=dict)
    source_type = Column(String(64), nullable=False, default="generated", index=True)
    privacy_level = Column(String(64), nullable=False, default="synthetic", index=True)
    synthetic = Column(Boolean, nullable=False, default=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SelectionEvalRun(Base):  # type: ignore
    __tablename__ = "selection_eval_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    background_job_id = Column(
        String(36),
        ForeignKey("background_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id = Column(String(255), nullable=False, index=True)
    dataset_version = Column(String(255), nullable=True, index=True)
    agent_id = Column(Integer, nullable=False, index=True)
    api_base = Column(String(512), nullable=True)
    worker_api_base = Column(String(512), nullable=True)
    dry_run = Column(Boolean, nullable=False, default=True, index=True)
    case_count = Column(Integer, nullable=False, default=0)
    passed = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    pass_rate = Column(Float, nullable=False, default=0.0)
    report_path = Column(Text, nullable=False, unique=True)
    by_loop = Column(JSON, nullable=True)
    budget = Column(JSON, nullable=True)
    summary_json = Column(JSON, nullable=False, default=dict)
    created_at_source = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    results = relationship(
        "SelectionEvalResult",
        back_populates="eval_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SelectionEvalResult(Base):  # type: ignore
    __tablename__ = "selection_eval_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    eval_run_id = Column(
        String(36),
        ForeignKey("selection_eval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id = Column(String(255), nullable=False, index=True)
    loop_type = Column(String(32), nullable=True, index=True)
    dataset_version = Column(String(255), nullable=True, index=True)
    task_id = Column(Integer, nullable=True, index=True)
    passed = Column(Boolean, nullable=False, default=False, index=True)
    score = Column(Float, nullable=True)
    transport = Column(JSON, nullable=True)
    judge = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    result_json = Column(JSON, nullable=False, default=dict)
    result_path = Column(Text, nullable=True)
    raw_output_path = Column(Text, nullable=True)
    failed_case_path = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    eval_run = relationship("SelectionEvalRun", back_populates="results")


class SelectionOutcome(Base):  # type: ignore
    __tablename__ = "selection_outcomes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    eval_run_id = Column(
        String(36),
        ForeignKey("selection_eval_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    case_id = Column(String(255), nullable=False, index=True)
    candidate_id = Column(String(255), nullable=True, index=True)
    loop_type = Column(String(32), nullable=True, index=True)
    dataset_version = Column(String(255), nullable=True, index=True)
    agent_recommendation = Column(String(64), nullable=True, index=True)
    actual_outcome = Column(String(64), nullable=True, index=True)
    hired = Column(Boolean, nullable=True)
    offer_accepted = Column(Boolean, nullable=True)
    performance_rating = Column(Float, nullable=True)
    retention_days = Column(Integer, nullable=True)
    outcome_date = Column(DateTime(timezone=True), nullable=True, index=True)
    source_type = Column(String(64), nullable=False, default="manual_import", index=True)
    privacy_level = Column(String(64), nullable=False, default="synthetic", index=True)
    synthetic = Column(Boolean, nullable=False, default=True, index=True)
    import_batch_id = Column(String(64), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    notes = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SelectionEvalBudgetStat(Base):  # type: ignore
    __tablename__ = "selection_eval_budget_stats"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scope = Column(String(255), nullable=False, index=True)
    jobs_started = Column(Integer, nullable=False, default=0)
    jobs_rejected_budget = Column(Integer, nullable=False, default=0)
    jobs_rejected_concurrency = Column(Integer, nullable=False, default=0)
    jobs_succeeded = Column(Integer, nullable=False, default=0)
    jobs_failed = Column(Integer, nullable=False, default=0)
    new_tasks_planned = Column(Integer, nullable=False, default=0)
    new_tasks_completed = Column(Integer, nullable=False, default=0)
    last_job_id = Column(String(36), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index(
    "ix_selection_eval_results_run_case",
    SelectionEvalResult.eval_run_id,
    SelectionEvalResult.case_id,
    unique=True,
)

Index(
    "ix_selection_outcomes_user_case_run",
    SelectionOutcome.user_id,
    SelectionOutcome.case_id,
    SelectionOutcome.eval_run_id,
)

Index(
    "ix_selection_loop_profiles_user_name_version",
    SelectionLoopProfile.user_id,
    SelectionLoopProfile.name,
    SelectionLoopProfile.version,
    unique=True,
)

Index(
    "ix_selection_loop_cases_user_case_dataset",
    SelectionLoopCase.user_id,
    SelectionLoopCase.case_id,
    SelectionLoopCase.dataset_version,
    unique=True,
)

Index(
    "ix_selection_eval_budget_stats_user_scope",
    SelectionEvalBudgetStat.user_id,
    SelectionEvalBudgetStat.scope,
    unique=True,
)
