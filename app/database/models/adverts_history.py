from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, ForeignKey, DateTime, Index
from sqlalchemy.orm import relationship

from app.database.models.base import Base

class AdvertHistory(Base):
    __tablename__ = 'adverts_history'

    id = Column(Integer, primary_key=True)
    ad_id = Column(BigInteger, ForeignKey('adverts.id'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    adverts = relationship("Advert", back_populates="advert_history")

    __table_args__ = (
        Index('idx_advert_history_created_at', created_at),
        Index('idx_advert_history_user_date', user_id, created_at),
        Index('idx_advert_history_ad_date', ad_id, created_at),
        Index('idx_advert_history_ad_id', ad_id),
    )