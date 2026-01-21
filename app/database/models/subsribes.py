from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, Boolean, String, Index
from sqlalchemy.orm import relationship

from app.database.models.base import Base

class Subscribe(Base):
    __tablename__ = 'subscribes'

    id = Column(Integer, primary_key=True)
    access = Column(String, nullable=True)
    is_bot = Column(Boolean, nullable=False)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    subscribe_count = Column(Integer, nullable=False)
    subscribed_count = Column(Integer, default=0)
    status = Column(Boolean, default=True)
    is_task = Column(Boolean, default=False)

    subscribe_history = relationship(
        "SubscribeHistory", 
        back_populates="subscribe",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_subscribes_status', status),
        Index('idx_subscribes_is_task', is_task),
        Index('idx_subscribes_url', url),
        Index('idx_subscribes_status_task', status, is_task),
    )