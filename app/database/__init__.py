import config

from flyerapi import Flyer

from app.database.pg_pool import DataBase
from app.database.redis_pool import RedisPool

flyer = Flyer(key=config.FLYER_API_KEY, debug=False)
db = DataBase(f"postgresql+asyncpg://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}")
redis_pool = RedisPool(url=F'redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}')