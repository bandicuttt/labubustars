from sqlalchemy.sql.schema import Column
from sqlalchemy.sql.sqltypes import Integer, String

from app.database.models.base import Base


class Settings(Base):
    __tablename__ = 'settings'

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=True)

