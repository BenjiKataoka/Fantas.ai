"""my_roster per league: key on user_leagues.id

Revision ID: b7c1d2e3f4a5
Revises: aef00b0b2978
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "b7c1d2e3f4a5"
down_revision = "aef00b0b2978"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_user_league", "user_leagues", ["user_id", "platform", "league_id"])

    op.add_column("my_roster", sa.Column("user_league_id", sa.Integer(), nullable=True))
    # Existing rows all came from the user's primary (last loaded) league.
    op.execute(
        "UPDATE my_roster r SET user_league_id = ul.id FROM user_leagues ul "
        "WHERE ul.user_id = r.user_id AND ul.is_primary"
    )
    op.execute("DELETE FROM my_roster WHERE user_league_id IS NULL")  # re-syncs on next load
    op.alter_column("my_roster", "user_league_id", nullable=False)
    op.create_foreign_key("fk_my_roster_user_league", "my_roster", "user_leagues",
                          ["user_league_id"], ["id"], ondelete="CASCADE")

    op.drop_constraint("my_roster_pkey", "my_roster", type_="primary")
    op.create_primary_key("my_roster_pkey", "my_roster", ["user_league_id", "player_id"])
    op.create_index("ix_my_roster_user_id", "my_roster", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_my_roster_user_id", "my_roster")
    op.drop_constraint("my_roster_pkey", "my_roster", type_="primary")
    # Keep one row per (user, player) so the old key fits again.
    op.execute(
        "DELETE FROM my_roster a USING my_roster b "
        "WHERE a.user_id = b.user_id AND a.player_id = b.player_id AND a.user_league_id > b.user_league_id"
    )
    op.create_primary_key("my_roster_pkey", "my_roster", ["user_id", "player_id"])
    op.drop_constraint("fk_my_roster_user_league", "my_roster", type_="foreignkey")
    op.drop_column("my_roster", "user_league_id")
    op.drop_constraint("uq_user_league", "user_leagues", type_="unique")
