import config

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
# Конфигурация Redis с обработкой пароля
redis_jobstore = {
    'host': config.REDIS_HOST,
    'port': config.REDIS_PORT,
    'db': config.REDIS_JOBSTORE_DB,
    'socket_timeout': 30  # Добавляем таймаут
}

job_stores = {
    'default': RedisJobStore(**redis_jobstore)
}

# Инициализация шедулера с обработкой ошибок
try:
    scheduler = AsyncIOScheduler(
        jobstores=job_stores,
        timezone="Europe/Moscow",
        job_defaults={
            'misfire_grace_time': 60,  # Допустимое время задержки
            'coalesce': True  # Объединять пропущенные выполнения
        }
    )
except Exception as e:
    raise RuntimeError(f"Failed to initialize scheduler: {str(e)}")
