import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Column, String, Boolean, TIMESTAMP, Integer, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator

from config import ESPN_COOKIE_KEY
from database import Base

logger = logging.getLogger(__name__)


class EncryptedString(TypeDecorator):
    """A string column the database only ever sees as ciphertext.

    Encrypts on write and decrypts on read, so every caller keeps using plain values.
    A value that will not decrypt (wrong or rotated key, or a row this never wrote)
    reads back as None rather than raising: the user row loads on every request, so a
    raise here would lock that user out of the whole app. None instead lands them in the
    ordinary "reconnect ESPN" state, which the bookmarklet fixes in one click.
    """
    impl = String
    cache_ok = True

    @staticmethod
    def _fernet() -> Fernet:
        if not ESPN_COOKIE_KEY:
            raise RuntimeError("ESPN_COOKIE_KEY is not set, so ESPN cookies cannot be stored.")
        return Fernet(ESPN_COOKIE_KEY.encode())

    def process_bind_param(self, value, dialect):
        return None if value is None else self._fernet().encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return self._fernet().decrypt(value.encode()).decode()
        except (InvalidToken, RuntimeError) as e:
            logger.error(f"[Auth] ESPN cookie would not decrypt ({type(e).__name__}); treating it as disconnected")
            return None


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
    espn_s2 = Column(EncryptedString, nullable=True)  # ESPN session cookie, encrypted at rest
    swid = Column(EncryptedString, nullable=True)     # ESPN account id cookie, encrypted at rest
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
