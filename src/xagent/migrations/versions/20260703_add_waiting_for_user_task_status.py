"""add waiting_for_user task status enum value

Revision ID: 20260703_add_waiting_for_user_task_status
Revises: 20260702_add_selection_eval_tables
Create Date: 2026-07-03 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260703_add_waiting_for_user_task_status"
down_revision: Union[str, tuple[str, str], None] = "20260702_add_selection_eval_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'WAITING_FOR_USER'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without rebuilding every
    # dependent column, so this downgrade intentionally leaves the value in place.
    pass
