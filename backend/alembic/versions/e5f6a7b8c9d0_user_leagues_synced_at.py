"""user_leagues.synced_at for portfolio staleness

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_leagues", sa.Column("synced_at", sa.TIMESTAMP(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_leagues", "synced_at")
