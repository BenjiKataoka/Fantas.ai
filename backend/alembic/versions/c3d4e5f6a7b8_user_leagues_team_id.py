"""user_leagues.team_id for ESPN public leagues

Revision ID: c3d4e5f6a7b8
Revises: b7c1d2e3f4a5
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b7c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_leagues", sa.Column("team_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_leagues", "team_id")
