"""Who asked for each exploration and whether it spent the daily allowance.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("explorations", sa.Column("client_key", sa.String(64), nullable=True))
    op.add_column(
        "explorations",
        sa.Column("counts_toward_limits", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_explorations_created_at", "explorations", ["created_at"])
    op.create_index(
        "ix_explorations_client_key_created_at", "explorations", ["client_key", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_explorations_client_key_created_at", table_name="explorations")
    op.drop_index("ix_explorations_created_at", table_name="explorations")
    op.drop_column("explorations", "counts_toward_limits")
    op.drop_column("explorations", "client_key")
