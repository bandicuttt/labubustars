from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, DateTime, String, JSON, Index

from app.database.models.base import Base

class ActionHistory(Base):
    __tablename__ = 'action_history'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    action_type = Column(String, nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Теперь индексы после объявления колонок!
    __table_args__ = (
        Index('idx_action_history_created_at', created_at),
        Index('idx_action_history_user_date', user_id, created_at),
        Index('idx_action_history_chat_date', chat_id, created_at),
        Index('idx_action_history_action_type', action_type),
        Index('idx_action_history_user_action', user_id, action_type),
    )