"""add selection outcomes table

Revision ID: 20260706_add_selection_outcomes
Revises: 20260703_add_waiting_for_user_task_status
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260706_add_selection_outcomes"
down_revision: Union[str, tuple[str, str], None] = (
    "20260703_add_waiting_for_user_task_status"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "selection_outcomes" not in tables:
        op.create_table(
            "selection_outcomes",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("eval_run_id", sa.String(length=36), nullable=True),
            sa.Column("case_id", sa.String(length=255), nullable=False),
            sa.Column("candidate_id", sa.String(length=255), nullable=True),
            sa.Column("loop_type", sa.String(length=32), nullable=True),
            sa.Column("dataset_version", sa.String(length=255), nullable=True),
            sa.Column("agent_recommendation", sa.String(length=64), nullable=True),
            sa.Column("actual_outcome", sa.String(length=64), nullable=True),
            sa.Column("hired", sa.Boolean(), nullable=True),
            sa.Column("offer_accepted", sa.Boolean(), nullable=True),
            sa.Column("performance_rating", sa.Float(), nullable=True),
            sa.Column("retention_days", sa.Integer(), nullable=True),
            sa.Column("outcome_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "source_type",
                sa.String(length=64),
                nullable=False,
                server_default="manual_import",
            ),
            sa.Column(
                "privacy_level",
                sa.String(length=64),
                nullable=False,
                server_default="synthetic",
            ),
            sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("import_batch_id", sa.String(length=64), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["eval_run_id"], ["selection_eval_runs.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    for index_name, columns in [
        ("ix_selection_outcomes_actual_outcome", ["actual_outcome"]),
        ("ix_selection_outcomes_agent_recommendation", ["agent_recommendation"]),
        ("ix_selection_outcomes_candidate_id", ["candidate_id"]),
        ("ix_selection_outcomes_case_id", ["case_id"]),
        ("ix_selection_outcomes_dataset_version", ["dataset_version"]),
        ("ix_selection_outcomes_eval_run_id", ["eval_run_id"]),
        ("ix_selection_outcomes_import_batch_id", ["import_batch_id"]),
        ("ix_selection_outcomes_loop_type", ["loop_type"]),
        ("ix_selection_outcomes_outcome_date", ["outcome_date"]),
        ("ix_selection_outcomes_privacy_level", ["privacy_level"]),
        ("ix_selection_outcomes_source_type", ["source_type"]),
        ("ix_selection_outcomes_synthetic", ["synthetic"]),
        ("ix_selection_outcomes_user_case_run", ["user_id", "case_id", "eval_run_id"]),
    ]:
        _create_index_if_missing("selection_outcomes", index_name, columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "selection_outcomes" in inspector.get_table_names():
        op.drop_table("selection_outcomes")


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing_indexes:
        op.create_index(index_name, table_name, columns)
