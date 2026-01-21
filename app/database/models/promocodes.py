from sqlalchemy import Boolean, Column, Integer, String, Float

from app.database.models.base import Base

class Promocode(Base):
    __tablename__ = 'promocodes'

    id = Column(Integer, primary_key=True)
    code = Column(String, nullable=False)
    status = Column(Boolean, default=True)
    activations = Column(Integer, default=0)
    activated = Column(Integer, default=0)
    amount = Column(Float, default=0.1)