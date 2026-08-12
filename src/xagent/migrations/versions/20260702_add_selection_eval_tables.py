"""add selection eval run/result tables

Revision ID: 20260702_add_selection_eval_tables
Revises: 20260624_add_mcp_concurrency_config
Create Date: 2026-07-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260702_add_selection_eval_tables"
down_revision: Union[str, tuple[str, str], None] = "20260624_add_mcp_concurrency_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "selection_eval_runs" not in tables:
        op.create_table(
            "selection_eval_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("background_job_id", sa.String(length=36), nullable=True),
            sa.Column("run_id", sa.String(length=255), nullable=False),
            sa.Column("dataset_version", sa.String(length=255), nullable=True),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("api_base", sa.String(length=512), nullable=True),
            sa.Column("worker_api_base", sa.String(length=512), nullable=True),
            sa.Column("dry_run", sa.Boolean(), nullable=False),
            sa.Column("case_count", sa.Integer(), nullable=False),
            sa.Column("passed", sa.Integer(), nullable=False),
            sa.Column("failed", sa.Integer(), nullable=False),
            sa.Column("pass_rate", sa.Float(), nullable=False),
            sa.Column("report_path", sa.Text(), nullable=False),
            sa.Column("by_loop", sa.JSON(), nullable=True),
            sa.Column("budget", sa.JSON(), nullable=True),
            sa.Column("summary_json", sa.JSON(), nullable=False),
            sa.Column("created_at_source", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["background_job_id"], ["background_jobs.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("report_path"),
        )

    if "selection_eval_results" not in tables:
        op.create_table(
            "selection_eval_results",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("eval_run_id", sa.String(length=36), nullable=False),
            sa.Column("case_id", sa.String(length=255), nullable=False),
            sa.Column("loop_type", sa.String(length=32), nullable=True),
            sa.Column("dataset_version", sa.String(length=255), nullable=True),
            sa.Column("task_id", sa.Integer(), nullable=True),
            sa.Column("passed", sa.Boolean(), nullable=False),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("transport", sa.JSON(), nullable=True),
            sa.Column("judge", sa.JSON(), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=True),
            sa.Column("result_json", sa.JSON(), nullable=False),
            sa.Column("result_path", sa.Text(), nullable=True),
            sa.Column("raw_output_path", sa.Text(), nullable=True),
            sa.Column("failed_case_path", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(
                ["eval_run_id"], ["selection_eval_runs.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    _create_index_if_missing("selection_eval_runs", "ix_selection_eval_runs_agent_id", ["agent_id"])
    _create_index_if_missing(
        "selection_eval_runs", "ix_selection_eval_runs_background_job_id", ["background_job_id"]
    )
    _create_index_if_missing(
        "selection_eval_runs", "ix_selection_eval_runs_dataset_version", ["dataset_version"]
    )
    _create_index_if_missing("selection_eval_runs", "ix_selection_eval_runs_dry_run", ["dry_run"])
    _create_index_if_missing("selection_eval_runs", "ix_selection_eval_runs_run_id", ["run_id"])

    _create_index_if_missing(
        "selection_eval_results", "ix_selection_eval_results_case_id", ["case_id"]
    )
    _create_index_if_missing(
        "selection_eval_results", "ix_selection_eval_results_dataset_version", ["dataset_version"]
    )
    _create_index_if_missing(
        "selection_eval_results", "ix_selection_eval_results_eval_run_id", ["eval_run_id"]
    )
    _create_index_if_missing(
        "selection_eval_results", "ix_selection_eval_results_loop_type", ["loop_type"]
    )
    _create_index_if_missing(
        "selection_eval_results", "ix_selection_eval_results_passed", ["passed"]
    )
    _create_index_if_missing(
        "selection_eval_results", "ix_selection_eval_results_task_id", ["task_id"]
    )
    _create_index_if_missing(
        "selection_eval_results",
        "ix_selection_eval_results_run_case",
        ["eval_run_id", "case_id"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "selection_eval_results" in tables:
        op.drop_table("selection_eval_results")
    if "selection_eval_runs" in tables:
        op.drop_table("selection_eval_runs")


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing_indexes:
        op.create_index(index_name, table_name, columns, unique=unique)
