"""add selection eval budget stats table

Revision ID: 20260706_add_selection_eval_budget_stats
Revises: 20260706_add_selection_loop_cases
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260706_add_selection_eval_budget_stats"
down_revision: Union[str, tuple[str, str], None] = "20260706_add_selection_loop_cases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "selection_eval_budget_stats" not in tables:
        op.create_table(
            "selection_eval_budget_stats",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("scope", sa.String(length=255), nullable=False),
            sa.Column("jobs_started", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("jobs_rejected_budget", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "jobs_rejected_concurrency",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("jobs_succeeded", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("jobs_failed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("new_tasks_planned", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("new_tasks_completed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_job_id", sa.String(length=36), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    for index_name, columns, unique in [
        ("ix_selection_eval_budget_stats_scope", ["scope"], False),
        ("ix_selection_eval_budget_stats_last_job_id", ["last_job_id"], False),
        (
            "ix_selection_eval_budget_stats_user_scope",
            ["user_id", "scope"],
            True,
        ),
    ]:
        _create_index_if_missing(
            "selection_eval_budget_stats",
            index_name,
            columns,
            unique=unique,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "selection_eval_budget_stats" in inspector.get_table_names():
        op.drop_table("selection_eval_budget_stats")


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
