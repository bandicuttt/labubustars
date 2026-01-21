from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.database.models.base import Base

class UserChat(Base):
    __tablename__ = 'user_chats'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    chat_id = Column(BigInteger, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    block_date = Column(DateTime(timezone=True), default=None)
    
    user = relationship("User", back_populates="user_chats")