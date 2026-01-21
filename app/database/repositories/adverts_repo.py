import json

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, or_, and_
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.utils.misc_function import get_time_now
from app.database.models import Advert, AdvertHistory
from app.database import redis_pool
from app.logger import logger


class AdvertRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_advert(self, **kwargs):
        chat = Advert(**kwargs)
        self.session.add(chat)
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def get_advert(self, advert_id: int) -> Advert | None:
        result = await self.session.execute(select(Advert).where(Advert.id == advert_id))
        return result.scalar_one_or_none()

    async def invalidate_adverts_cache(self):
        """Сбрасываем кэш активной рекламы (при изменении статуса)"""
        async with redis_pool.get_connection() as conn:
            await conn.delete("active_adverts")

    async def get_all_adverts(self, count: bool = True):
        query = select(func.count()).select_from(Advert) if count else select(Advert).order_by(Advert.id)
        result = await self.session.execute(query)
        return result.scalars().all() if not count else result.scalar()

    async def update_advert(self, advert_id: int, **kwargs):
        advert = await self.get_advert(advert_id)
        for key, value in kwargs.items():
            setattr(advert, key, value)
        await self.session.commit()  # ← Есть
        await self.session.refresh(advert)
        await self.invalidate_adverts_cache()  # ← Добавляем инвалидацию!
        return advert
    
    async def delete_advert(self, advert_id: int):
        advert = await self.get_advert(advert_id)
        if advert:
            await self.session.delete(advert)
            await self.session.commit()
            return True
        return False

    async def get_advert_by_id(self, advert_id: int) -> Advert | None:
        query = select(Advert).where(Advert.id == advert_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_advert_views(self, advert_id: int) -> Advert:
        query = update(Advert).where(Advert.id == advert_id).values(
            viewed=Advert.viewed + 1
        )
        await self.session.execute(query)
        await self.session.commit()

        return await self.get_advert_by_id(advert_id)

    async def mark_advert_shown(self, user_id: int, advert_id: int):
        async with redis_pool.get_connection() as conn:
            # 1. Ключ временного промежутка 3 часа
            time_key = f"advert:{advert_id}:user:{user_id}:time"
            await conn.setex(time_key, 10800, "1")  # 3 часа = 10800 секунд
            
            # 2. Ключ количества показов 7 дней
            count_key = f"advert:{advert_id}:user:{user_id}:count"
            await conn.incr(count_key)
            await conn.expire(count_key, 604800)  # 7 дней = 604800 секунд
    
    async def get_active_adverts(self) -> list[tuple]:
        async with redis_pool.get_connection() as conn:
            cache_key = "active_adverts"
            cached_data = await conn.get(cache_key)
            
            if cached_data:
                adverts_data = json.loads(cached_data)
                return [
                    (int(advert_id), advert_only_start, uniq_filter)
                    for advert_id, (advert_only_start, uniq_filter) in adverts_data.items()
                ]
            
            query = select(Advert).where(
                Advert.status == True,
                Advert.viewed < Advert.views
            )

            result = await self.session.execute(query)
            adverts = result.scalars().all()

            if not adverts:
                adverts_data = {}
            else:
                adverts_data = {
                    str(advert.id): [advert.only_start, advert.uniq_filter] 
                    for advert in adverts
                }

            await conn.setex(cache_key, 300, json.dumps(adverts_data))
            
            return [
                (advert.id, advert.only_start, advert.uniq_filter)
                for advert in adverts
            ]

    async def _can_show_advert_to_user(self, user_id: int, advert_id: int, uniq_filter: int) -> bool:
        async with redis_pool.get_connection() as conn:
            # 1. Проверяем временной промежуток 3 часа
            time_key = f"advert:{advert_id}:user:{user_id}:time"
            last_shown = await conn.get(time_key)
            if last_shown:
                return False  # Уже показывали менее 3 часов назад
            
            # 2. Проверяем общее количество показов (uniq_filter)
            count_key = f"advert:{advert_id}:user:{user_id}:count"
            current_count = await conn.get(count_key)
            if current_count and int(current_count) >= uniq_filter:
                return False  # Достигнут лимит показов на юзера
            
            return True 
    
    async def get_advert_for_user(self, user_id: int, only_start: bool = False) -> Advert | None:
        active_adverts = await self.get_active_adverts()
        
        for advert_id, advert_only_start, uniq_filter in active_adverts:

            if only_start:
                if not advert_only_start:
                    continue  # Пропускаем если нужно only_start но у рекламы False
                return await self.get_advert_by_id(advert_id)
            if not only_start and advert_only_start:
                continue  # Пропускаем если НЕ нужно only_start но у рекламы True
                
            can_show = await self._can_show_advert_to_user(user_id, advert_id, uniq_filter)
            if can_show:
                return await self.get_advert_by_id(advert_id)
        
        return None
