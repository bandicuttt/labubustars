from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, Boolean, JSON, String
from sqlalchemy.orm import relationship

from app.database.models.base import Base

class Advert(Base):
    __tablename__ = 'adverts'

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    message_id = Column(BigInteger, nullable=False)
    from_chat_id = Column(BigInteger, nullable=False)
    reply_markup = Column(JSON, nullable=True)
    uniq_filter = Column(Integer, nullable=False)
    views = Column(Integer, default=0)
    viewed = Column(Integer, default=0)
    status = Column(Boolean, default=True)
    only_start = Column(Boolean, nullable=False)

    advert_history = relationship(
        "AdvertHistory", 
        back_populates="adverts",
        cascade="all, delete-orphan"
    )