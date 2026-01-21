from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship

from app.database.models.base import Base

class SubscribeHistory(Base):
    __tablename__ = 'subscribe_history'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    sub_id = Column(Integer, ForeignKey('subscribes.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subscribe = relationship("Subscribe", back_populates="subscribe_history")

    __table_args__ = (
        Index('idx_subscribe_history_created_at', created_at),
        Index('idx_subscribe_history_user_date', user_id, created_at),
        Index('idx_subscribe_history_sub_id', sub_id),
        Index('idx_subscribe_history_sub_date', sub_id, created_at),
    )