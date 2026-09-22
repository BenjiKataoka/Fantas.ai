from sqlalchemy import Column, String, Boolean, TIMESTAMP, Integer, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    """App users, each must be approved before accessing the app."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    clerk_id = Column(String, unique=True, nullable=False)  # Clerk's user ID
    email = Column(String, unique=True, nullable=False)
    username = Column(String, unique=True, nullable=False)
    is_approved = Column(Boolean, default=False, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    approved_at = Column(TIMESTAMP, nullable=True)

    # Sleeper credentials (platform-level, not league-level)
    sleeper_username = Column(String, nullable=True)
    sleeper_user_id = Column(String, nullable=True)   # Fetched from Sleeper API on save

    # ESPN credentials (only needed if user's league is on ESPN)
    espn_s2 = Column(String, nullable=True)           # Cookie, treat as sensitive
    swid = Column(String, nullable=True)              # Cookie, treat as sensitive
    # Set when ESPN rejects the saved cookies (sync or page load); drives the reconnect
    # banner. Cleared when the user saves fresh cookies or disconnects.
    espn_needs_reconnect = Column(Boolean, default=False, nullable=False, server_default="false")

    # Per-user projection source weights
    weight_sleeper = Column(Float, default=0.35, nullable=False)
    weight_espn = Column(Float, default=0.30, nullable=False)
    weight_fp = Column(Float, default=0.35, nullable=False)

    # Relationships
    roster = relationship("MyRoster", back_populates="user")
    tracked_players = relationship("TrackedPlayer", back_populates="user")
    leagues = relationship("UserLeague", back_populates="user")


class UserLeague(Base):
    """All fantasy leagues a user has connected, across all platforms.
    is_primary=True marks the league loaded most recently (the server-side default when
    a request doesn't name one)."""
    __tablename__ = "user_leagues"
    __table_args__ = (UniqueConstraint("user_id", "platform", "league_id", name="uq_user_league"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(String, nullable=False)         # SLEEPER or ESPN
    league_id = Column(String, nullable=False)
    league_name = Column(String, nullable=True)
    total_rosters = Column(Integer, nullable=True)    # League size
    season = Column(Integer, nullable=True)
    is_primary = Column(Boolean, default=False, nullable=False)
    # ESPN public leagues only: which team is yours, since without cookies there's no SWID
    # to match. Null means "find my team by SWID".
    team_id = Column(Integer, nullable=True)
    synced_at = Column(TIMESTAMP, nullable=True)      # last roster sync; the portfolio re-syncs stale leagues
    connected_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="leagues")
