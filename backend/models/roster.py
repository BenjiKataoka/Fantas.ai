from sqlalchemy import Column, String, Boolean, Date, Integer, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class MyRoster(Base):
    """Per-user, per-league roster. A player on two of your teams has two rows, one per
    league, so cross-league readers must dedupe on player_id."""
    __tablename__ = "my_roster"

    # Points at user_leagues (not a raw league id) so the platform travels with it: a
    # Sleeper and an ESPN league id could collide.
    user_league_id = Column(Integer, ForeignKey("user_leagues.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    acquisition_date = Column(Date, nullable=True)
    is_starter = Column(Boolean, default=False, nullable=False)

    # Starting lineup slot (QB/RB1/RB2/WR1/WR2/TE/FLEX/K/BN)
    slot = Column(String, nullable=True)

    # Relationships
    user = relationship("User", back_populates="roster")
    player = relationship("Player")
