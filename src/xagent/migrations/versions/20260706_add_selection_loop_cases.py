"""add selection loop cases table

Revision ID: 20260706_add_selection_loop_cases
Revises: 20260706_add_selection_loop_profiles
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260706_add_selection_loop_cases"
down_revision: Union[str, tuple[str, str], None] = "20260706_add_selection_loop_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "selection_loop_cases" not in tables:
        op.create_table(
            "selection_loop_cases",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("profile_id", sa.String(length=36), nullable=True),
            sa.Column("case_id", sa.String(length=255), nullable=False),
            sa.Column("loop_type", sa.String(length=32), nullable=True),
            sa.Column("dataset_version", sa.String(length=255), nullable=True),
            sa.Column("case_path", sa.Text(), nullable=True),
            sa.Column("prompt_path", sa.Text(), nullable=True),
            sa.Column("prompt_text", sa.Text(), nullable=True),
            sa.Column("quality_passed", sa.Boolean(), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=True),
            sa.Column("expected_output", sa.JSON(), nullable=True),
            sa.Column("case_json", sa.JSON(), nullable=False),
            sa.Column(
                "source_type",
                sa.String(length=64),
                nullable=False,
                server_default="generated",
            ),
            sa.Column(
                "privacy_level",
                sa.String(length=64),
                nullable=False,
                server_default="synthetic",
            ),
            sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["profile_id"], ["selection_loop_profiles.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    for index_name, columns, unique in [
        ("ix_selection_loop_cases_case_id", ["case_id"], False),
        ("ix_selection_loop_cases_dataset_version", ["dataset_version"], False),
        ("ix_selection_loop_cases_is_active", ["is_active"], False),
        ("ix_selection_loop_cases_loop_type", ["loop_type"], False),
        ("ix_selection_loop_cases_privacy_level", ["privacy_level"], False),
        ("ix_selection_loop_cases_profile_id", ["profile_id"], False),
        ("ix_selection_loop_cases_quality_passed", ["quality_passed"], False),
        ("ix_selection_loop_cases_source_type", ["source_type"], False),
        ("ix_selection_loop_cases_synthetic", ["synthetic"], False),
        (
            "ix_selection_loop_cases_user_case_dataset",
            ["user_id", "case_id", "dataset_version"],
            True,
        ),
    ]:
        _create_index_if_missing(
            "selection_loop_cases",
            index_name,
            columns,
            unique=unique,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "selection_loop_cases" in inspector.get_table_names():
        op.drop_table("selection_loop_cases")


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
