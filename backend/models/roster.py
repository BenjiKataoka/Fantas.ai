from sqlalchemy import Column, String, Boolean, Date, Integer, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class MyRoster(Base):
    """Per-user roster — which players each user owns in their fantasy league."""
    __tablename__ = "my_roster"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    player_id = Column(String, ForeignKey("players.player_id"), primary_key=True)
    acquisition_date = Column(Date, nullable=True)
    is_starter = Column(Boolean, default=False, nullable=False)

    # Starting lineup slot (QB/RB1/RB2/WR1/WR2/TE/FLEX/K/BN)
    slot = Column(String, nullable=True)

    # Relationships
    user = relationship("User", back_populates="roster")
    player = relationship("Player")
