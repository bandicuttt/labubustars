from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Float, Integer, String, BigInteger, Boolean, DateTime, Index
from sqlalchemy.orm import relationship

from app.database.models.base import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    user_name = Column(String, nullable=True)
    user_fullname = Column(String, nullable=False)
    is_premium = Column(Boolean, nullable=False)
    block_date = Column(DateTime(timezone=True), default=None)
    created_at = Column(DateTime(timezone=True), default=func.now())
    ref = Column(String, nullable=True)
    subbed = Column(Boolean, default=False)
    subbed_second = Column(Boolean, default=False)
    balance = Column(Float, default=0)
    last_activity = Column(DateTime(timezone=True), default=None)
    is_inactive = Column(Boolean, default=False)
    reactivation_count = Column(Integer, default=0)
    # TODO: SQL ADD COLUMN FOR ALL UNDER THIS LINE
    darts_op_count = Column(Integer, default=0)
    dart_gift_received = Column(Boolean, default=False)
    banned = Column(Boolean, default=False)

    user_chats = relationship("UserChat", back_populates="user")
    payments = relationship("Payment", back_populates="user")

    __table_args__ = (
        Index('idx_users_block_date', block_date),
        Index('idx_users_subbed', subbed),
        Index('idx_users_ref', ref),
        Index('idx_users_created_at', created_at),
    )
