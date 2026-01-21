from sqlalchemy import Column, String, Integer, Float

from app.database.models.base import Base


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True)
    ref = Column(String, nullable=False)
    total_visits = Column(Integer, default=0)
    total_uniq_visits = Column(Integer, default=0)
    price = Column(Float)
    admin_url = Column(String)
