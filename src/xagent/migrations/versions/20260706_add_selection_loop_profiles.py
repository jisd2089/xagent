"""add selection loop profiles table

Revision ID: 20260706_add_selection_loop_profiles
Revises: 20260706_add_selection_outcomes
Create Date: 2026-07-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260706_add_selection_loop_profiles"
down_revision: Union[str, tuple[str, str], None] = "20260706_add_selection_outcomes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "selection_loop_profiles" not in tables:
        op.create_table(
            "selection_loop_profiles",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("job_family", sa.String(length=128), nullable=True),
            sa.Column("job_title", sa.String(length=255), nullable=True),
            sa.Column("level", sa.String(length=64), nullable=True),
            sa.Column("locale", sa.String(length=64), nullable=True),
            sa.Column("profile_json", sa.JSON(), nullable=False),
            sa.Column("source_type", sa.String(length=64), nullable=False, server_default="manual"),
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
            sa.PrimaryKeyConstraint("id"),
        )

    for index_name, columns, unique in [
        ("ix_selection_loop_profiles_is_active", ["is_active"], False),
        ("ix_selection_loop_profiles_job_family", ["job_family"], False),
        ("ix_selection_loop_profiles_job_title", ["job_title"], False),
        ("ix_selection_loop_profiles_level", ["level"], False),
        ("ix_selection_loop_profiles_name", ["name"], False),
        ("ix_selection_loop_profiles_privacy_level", ["privacy_level"], False),
        ("ix_selection_loop_profiles_source_type", ["source_type"], False),
        ("ix_selection_loop_profiles_synthetic", ["synthetic"], False),
        (
            "ix_selection_loop_profiles_user_name_version",
            ["user_id", "name", "version"],
            True,
        ),
    ]:
        _create_index_if_missing(
            "selection_loop_profiles",
            index_name,
            columns,
            unique=unique,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "selection_loop_profiles" in inspector.get_table_names():
        op.drop_table("selection_loop_profiles")


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
