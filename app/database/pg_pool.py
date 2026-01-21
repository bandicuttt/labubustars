import config

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.database.models.base import Base


class DataBase:
    def __init__(self, database_url: str):
        self.engine = create_async_engine(
            database_url,
            echo=True if config.PG_DEBUG_MODE else False,
            pool_size=30,  # Максимальное количество постоянных соединений
            max_overflow=20,  # Дополнительные временные соединения при пиковой нагрузке
            pool_timeout=30,  # Таймаут ожидания доступного соединения
            pool_recycle=1800,  # Пересоздание соединений каждые 30 минут
            connect_args={"server_settings": {"timezone": config.TIMEZONE}}
            )
        self.async_session = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]: 
        async with self.async_session() as session:
            yield session
            
    async def check_and_create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)