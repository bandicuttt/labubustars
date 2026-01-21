from redis.asyncio import Redis, ConnectionPool
from typing import Optional
from contextlib import asynccontextmanager

from config import REDIS_DEBUG_MODE

class RedisPool:
    _instance: Optional['RedisPool'] = None
    _pool: Optional[ConnectionPool] = None
    _redis: Optional[Redis] = None
    _url: Optional[str] = None

    def __init__(self, url: str = 'redis://localhost/0'):
        if not self._url: 
            self._url = url

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def init_pool(self):
        if self._pool is None:
            self._pool = ConnectionPool.from_url(
                self._url,
                encoding='utf-8',
                decode_responses=REDIS_DEBUG_MODE
            )
            self._redis = Redis(connection_pool=self._pool)

    @asynccontextmanager
    async def get_connection(self):
        if self._pool is None:
            await self.init_pool()
        try:
            yield self._redis
        except Exception as e:
            print(f"Redis error: {e}")
            raise
        finally:
            # Не закрываем соединение - оно управляется пулом
            pass

    async def close(self):
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None