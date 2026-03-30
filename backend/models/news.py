from sqlalchemy import Column, String, Boolean, Text, Integer, Float, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class PlayerNews(Base):
    """Raw news items scraped from RotoWire, ESPN, Sleeper, and NFL transactions."""
    __tablename__ = "player_news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("players.player_id"), nullable=False)
    source = Column(String, nullable=False)         # ROTOWIRE/ESPN/SLEEPER/NFL_TRANS
    headline = Column(Text, nullable=False)
    news_body = Column(Text, nullable=True)         # Max 2000 chars
    published_at = Column(TIMESTAMP, nullable=True)
    source_url = Column(Text, nullable=True)
    news_type = Column(String, nullable=True)       # INJURY/CONTRACT/PERFORMANCE/DEPTH_CHART/TRANSACTION/GENERAL
    is_rostered = Column(Boolean, default=False)    # Is this player on any user's roster?
    analysis_status = Column(String, default="PENDING")  # PENDING/COMPLETE/SKIPPED
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    player = relationship("Player", back_populates="news")
    analysis = relationship("NewsAnalysis", back_populates="news_item", uselist=False)


class NewsAnalysis(Base):
    """Gemini 2-pass AI analysis result for a single news item."""
    __tablename__ = "news_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    news_id = Column(Integer, ForeignKey("player_news.id"), unique=True, nullable=False)
    player_id = Column(String, ForeignKey("players.player_id"), nullable=False)

    summary = Column(Text, nullable=True)                    # 2-3 sentence plain English summary
    stock_direction = Column(String, nullable=True)          # BULLISH/BEARISH/NEUTRAL
    stock_magnitude = Column(String, nullable=True)          # HIGH/MEDIUM/LOW
    confidence_score = Column(Float, nullable=True)          # 0.0-1.0
    short_term_impact = Column(Text, nullable=True)
    long_term_impact = Column(Text, nullable=True)
    context_notes = Column(Text, nullable=True)
    contradictions_flagged = Column(Boolean, default=False)
    contradiction_detail = Column(Text, nullable=True)
    analysis_model = Column(String, nullable=True)           # Which Gemini model was used
    generated_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    news_item = relationship("PlayerNews", back_populates="analysis")


class NewsHistoryContext(Base):
    """Rolling 500-word context summary of the last 10 news items per player.
    Regenerated after each new news item — used as Pass 2 input for the news analyzer."""
    __tablename__ = "news_history_context"

    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    context_summary = Column(Text, nullable=True)
    last_updated = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


class BeatWriterSentiment(Base):
    """Beat writer and media sentiment scraped from various sources."""
    __tablename__ = "beat_writer_sentiment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("players.player_id"), nullable=False)
    source_name = Column(String, nullable=True)
    headline = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    sentiment = Column(String, nullable=True)       # POSITIVE/NEGATIVE/NEUTRAL
    published_at = Column(TIMESTAMP, nullable=True)
    scraped_at = Column(TIMESTAMP, server_default=func.now())
