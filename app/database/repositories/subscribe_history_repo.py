from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, distinct, exists

from app.utils.misc_function import get_time_now
from app.database import models


class SubscriptionHistoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_subscription_history(self, **kwargs):
        subscription_history = models.SubscribeHistory(**kwargs)
        self.session.add(subscription_history)
        await self.session.commit()
        await self.session.refresh(subscription_history)
        return subscription_history

    async def get_user_subscription_history(self, user_id: int):
        query = select(models.SubscribeHistory).where(
            models.SubscribeHistory.user_id == user_id
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_user_subscription_ids(self, user_id: int):
        three_months_ago = get_time_now() - timedelta(days=90)
        query = select(models.SubscribeHistory).join(
            models.Subscribe,
            models.SubscribeHistory.sub_id == models.Subscribe.id
        ).where(
            models.SubscribeHistory.user_id == user_id,
            models.Subscribe.status == True,
            models.SubscribeHistory.created_at >= three_months_ago
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_user_subscribe_ids(self, user_id: int) -> list[int]:
        """Get list of subscribe IDs that user has completed"""
        query = select(models.SubscribeHistory.sub_id).where(
            models.SubscribeHistory.user_id == user_id
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def check_subscription_exists(self, user_id: int, sub_id: int) -> bool:
        """Проверяет, существует ли уже запись о подписке пользователя"""
        query = select(exists().where(
            models.SubscribeHistory.user_id == user_id,
            models.SubscribeHistory.sub_id == sub_id
        ))
        result = await self.session.execute(query)
        return result.scalar()

    async def update_subscribers_count(self, sub_id: int):
        """Обновляет количество уникальных подписчиков для конкретной подписки"""
        query = select(func.count(distinct(models.SubscribeHistory.user_id))).where(
            models.SubscribeHistory.sub_id == sub_id
        )
        result = await self.session.execute(query)
        unique_subscribers = result.scalar()

        update_query = select(models.Subscribe).where(models.Subscribe.id == sub_id)
        result = await self.session.execute(update_query)
        subscribe = result.scalar_one()
        subscribe.subscribed_count = unique_subscribers
    
        if subscribe.subscribed_count >= subscribe.subscribe_count:
            subscribe.status = False

        await self.session.commit()

    async def delete_subscription_history(self, sub_id: int):
        query = select(models.SubscribeHistory).where(
            models.SubscribeHistory.sub_id == sub_id
        )
        result = await self.session.execute(query)
        subscription_history = result.scalars().all()
        for history in subscription_history:
            self.session.delete(history)
