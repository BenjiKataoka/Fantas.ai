from sqlalchemy import Column, String, Float, Integer, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Projection(Base):
    """Weekly projections per player from all three sources + weighted result."""
    __tablename__ = "projections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("players.player_id"), nullable=False)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)

    # Raw projections from each source (null if source unavailable)
    sleeper_proj = Column(Float, nullable=True)
    espn_proj = Column(Float, nullable=True)
    fp_proj = Column(Float, nullable=True)

    # Weighted result
    weighted_proj = Column(Float, nullable=True)

    # Which sources actually contributed (e.g. {"sleeper": 0.5, "fp": 0.5} if ESPN failed)
    sources_used = Column(JSONB, nullable=True)

    # HIGH = all 3 sources present, MEDIUM = 2 sources, LOW = 1 source
    confidence_flag = Column(String, nullable=True)

    last_updated = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relationships
    player = relationship("Player", back_populates="projections")
