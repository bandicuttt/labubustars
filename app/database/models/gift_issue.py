from sqlalchemy.sql import func
from sqlalchemy import Column, Integer, BigInteger, DateTime, Index

from app.database.models.base import Base


class GiftIssue(Base):
    __tablename__ = "gift_issues"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False, unique=True)
    total_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_gift_issues_user_id", user_id),
    )
