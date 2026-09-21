from sqlalchemy import Column, String, Boolean, Text, Integer, Float, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class TrackedPlayer(Base):
    """Per-user watchlist, any NFL player a user has starred."""
    __tablename__ = "tracked_players"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    player_name = Column(String, nullable=False)
    position = Column(String, nullable=True)
    nfl_team = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    years_exp = Column(Integer, nullable=True)
    depth_chart_pos = Column(String, nullable=True)   # starter/backup
    contract_year = Column(Boolean, default=False)
    starred_at = Column(TIMESTAMP, server_default=func.now())
    star_notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    # Relationships
    user = relationship("User", back_populates="tracked_players")
    player = relationship("Player")
    stock_profile = relationship(
        "PlayerStockProfile",
        primaryjoin="TrackedPlayer.player_id == foreign(PlayerStockProfile.player_id)",
        uselist=False,
        viewonly=True,
    )


class PlayerHistoricalStats(Base):
    """Season-level historical stats per tracked player, loaded from nflreadpy."""
    __tablename__ = "player_historical_stats"

    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    season = Column(Integer, primary_key=True)
    games_played = Column(Integer, nullable=True)
    fantasy_pts_ppr = Column(Float, nullable=True)
    fantasy_ppg_ppr = Column(Float, nullable=True)
    targets = Column(Integer, nullable=True)
    receptions = Column(Integer, nullable=True)
    rec_yards = Column(Integer, nullable=True)
    rec_td = Column(Integer, nullable=True)
    carries = Column(Integer, nullable=True)
    rush_yards = Column(Integer, nullable=True)
    rush_td = Column(Integer, nullable=True)
    pass_yards = Column(Integer, nullable=True)
    pass_td = Column(Integer, nullable=True)
    interceptions = Column(Integer, nullable=True)
    snap_pct_avg = Column(Float, nullable=True)

    # Relationships
    player = relationship("Player", back_populates="historical_stats")


class PlayerADPHistory(Base):
    """Daily ADP snapshots per player from FFC and FantasyPros.
    Keeps 30 days of history for trend calculation."""
    __tablename__ = "player_adp_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("players.player_id"), nullable=False)
    source = Column(String, nullable=False)           # FFC/FANTASYPROS/ESPN/SEED
    adp = Column(Float, nullable=True)
    adp_stdev = Column(Float, nullable=True)
    position_rank = Column(Integer, nullable=True)    # in-season: derived from ESPN weekly projections
    overall_rank = Column(Integer, nullable=True)
    percent_rostered = Column(Float, nullable=True)   # ESPN % rostered, live in-season momentum
    recorded_at = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    player = relationship("Player", back_populates="adp_history")


class PlayerStockProfile(Base):
    """Full 4-pass Gemini stock analysis result for a tracked player.
    One row per player, updated on re-analysis."""
    __tablename__ = "player_stock_profile"

    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Pass 2, overall stock
    overall_direction = Column(String, nullable=True)    # BULLISH/BEARISH/NEUTRAL
    overall_magnitude = Column(String, nullable=True)    # HIGH/MEDIUM/LOW

    # Pass 3, concern score
    concern_level = Column(Integer, nullable=True)       # 1-10
    concern_summary = Column(Text, nullable=True)        # One direct sentence
    worry_score = Column(Integer, nullable=True)         # 1-10 (current news cycle)
    combined_score = Column(Float, nullable=True)        # Weighted final score
    bullish_factors = Column(JSONB, nullable=True)
    bearish_factors = Column(JSONB, nullable=True)

    # ADP trend
    adp_trend = Column(String, nullable=True)            # RISING/FALLING/STABLE
    adp_trend_delta = Column(Float, nullable=True)       # 14-day change

    # Pass 4, sentiment
    sentiment_score = Column(Float, nullable=True)       # -1.0 to 1.0
    sentiment_label = Column(String, nullable=True)
    sentiment_confidence = Column(Float, nullable=True)
    news_volume = Column(String, nullable=True)          # HIGH/MEDIUM/LOW
    dominant_themes = Column(JSONB, nullable=True)
    sentiment_vs_stock = Column(String, nullable=True)   # CONFIRMS/STRENGTHENS/WEAKENS/CONTRADICTS
    alignment_note = Column(Text, nullable=True)
    contrarian_flag = Column(Boolean, default=False)

    # Pass 1, historical
    historical_context = Column(Text, nullable=True)     # 200-word career summary
    short_term_outlook = Column(Text, nullable=True)
    long_term_outlook = Column(Text, nullable=True)
    draft_recommendation = Column(String, nullable=True) # EARLY_TARGET/FAIR_VALUE/LATE_ROUND/AVOID/WATCHLIST_ONLY

    last_full_analysis = Column(TIMESTAMP, nullable=True)
    last_news_update = Column(TIMESTAMP, nullable=True)

    # Relationships
    # Access tracked_player via TrackedPlayer.stock_profile (viewonly relationship above)


class PlayerSentimentHistory(Base):
    """Append-only sentiment snapshots per player, one row per completed analysis.

    Unlike player_stock_profile (which is overwritten each run to hold the CURRENT
    values), this table keeps every dated point so we can chart sentiment over time.
    Global (no user_id), matching the global stock profile. Mirrors player_adp_history.
    """
    __tablename__ = "player_sentiment_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String, ForeignKey("players.player_id"), nullable=False, index=True)
    sentiment_score = Column(Float, nullable=True)      # -1.0..1.0: the primary line
    sentiment_label = Column(String, nullable=True)
    concern_level = Column(Integer, nullable=True)      # 1-10, optional overlay line
    worry_score = Column(Integer, nullable=True)        # 1-10
    combined_score = Column(Float, nullable=True)
    overall_direction = Column(String, nullable=True)   # BULLISH/BEARISH/NEUTRAL, point color
    recorded_at = Column(TIMESTAMP, server_default=func.now(), index=True)
