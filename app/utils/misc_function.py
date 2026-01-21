import pytz
import config
import json

from datetime import datetime, timedelta

from app.database import redis_pool

def get_time_now():
    """Возвращает текущее время с временной зоной из конфига"""
    return datetime.now(pytz.timezone(config.TIMEZONE))

async def get_remaining_time():
    """Возвращает оставшееся время лотереи в формате HH:MM:SS"""
    async with redis_pool.get_connection() as redis_conn:
        data = await redis_conn.get('lottery_start')
    
    if not data:
        return str(timedelta(seconds=config.LOTTERY_TTL))
    
    lottery_data = json.loads(data)
    start_time = datetime.fromisoformat(lottery_data['start_time'])
    expired_time = lottery_data['expired_time']

    start_time = datetime.fromisoformat(lottery_data['start_time'])
    expired_time = timedelta(seconds=lottery_data['expired_time'])

    now = datetime.now(pytz.timezone(config.TIMEZONE))
    end_time = start_time + expired_time
    remaining = end_time - now

    if remaining.total_seconds() <= 0:
        return str(timedelta(seconds=config.LOTTERY_TTL))
    
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"