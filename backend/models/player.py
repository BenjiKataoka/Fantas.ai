from sqlalchemy import Column, String, Float, Integer, Boolean, Text, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Player(Base):
    """Global NFL player pool, shared across all users."""
    __tablename__ = "players"

    player_id = Column(String, primary_key=True)  # Sleeper ID as canonical
    name = Column(String, nullable=False)
    position = Column(String)                      # QB/RB/WR/TE/K
    nfl_team = Column(String)
    sleeper_id = Column(String)
    espn_id = Column(String)
    espn_athlete_id = Column(String)               # For ESPN sports API
    fp_name = Column(String)                       # FantasyPros display name
    injury_status = Column(String)                 # Active/Questionable/Doubtful/Out/IR
    injury_detail = Column(Text)
    last_updated = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    projections = relationship("Projection", back_populates="player")
    news = relationship("PlayerNews", back_populates="player")
    historical_stats = relationship("PlayerHistoricalStats", back_populates="player")
    adp_history = relationship("PlayerADPHistory", back_populates="player")
