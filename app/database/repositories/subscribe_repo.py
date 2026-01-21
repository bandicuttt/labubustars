import config

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.sql.base import NO_ARG

from app.database import models
from app.database.repositories.subscribe_history_repo import SubscriptionHistoryRepository

class SubscribeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_subscribe(self, **kwargs):
        chat = models.Subscribe(**kwargs)
        self.session.add(chat)
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def get_subscribe(self, sub_id: int):
        result = await self.session.execute(select(models.Subscribe).where(models.Subscribe.id == sub_id))
        return result.scalar_one_or_none()

    async def get_all_subscribes_total(self, count: bool = True):
        query = select(func.count()).select_from(models.Subscribe) if count else select(models.Subscribe).order_by(models.Subscribe.id)

        result = await self.session.execute(query)
        return result.scalars().all() if not count else result.scalar()

    async def get_all_subscribes(self, 
        count: bool = True,
        is_task: bool = False,
        get_all: bool = False,
        limit: int | None = None
    ):
        if count:
            query = select(func.count()).select_from(models.Subscribe)
        else:
            query = select(models.Subscribe).order_by(models.Subscribe.id)
            if limit:
                query = query.limit(limit)

        filters = [models.Subscribe.status == True]
        if not get_all:
            filters.append(models.Subscribe.is_task == is_task)

        query = query.where(*filters)
        result = await self.session.execute(query)
        return result.scalar() if count else result.scalars().all()

    async def update_subscribe(self, sub_id: int, **kwargs):
        sub = await self.get_subscribe(sub_id)
        for key, value in kwargs.items():
            setattr(sub, key, value)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def get_active_tasks(self, user_id: int):
        """Get active tasks that user hasn't completed yet"""
        # Get completed task IDs for this user

        history_repo = SubscriptionHistoryRepository(self.session)
        completed_task_ids = await history_repo.get_user_subscribe_ids(user_id)
        
        # Query tasks excluding completed ones
        query = select(models.Subscribe).order_by(models.Subscribe.id).where(
            models.Subscribe.status == True,
            models.Subscribe.subscribe_count > models.Subscribe.subscribed_count,
            models.Subscribe.is_task == True,
            models.Subscribe.access is not None,
            models.Subscribe.id.not_in(completed_task_ids) if completed_task_ids else True
        )
        
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_active_sponsors_batch(self, user_id: int, limit: int, page: int):
        offset = page * limit
        history_repo = SubscriptionHistoryRepository(self.session)
        # completed_task_ids = await history_repo.get_user_subscribe_ids(user_id)

        query = (
            select(models.Subscribe)
            .order_by(models.Subscribe.id)
            .where(
                models.Subscribe.status == True,
                models.Subscribe.subscribe_count > models.Subscribe.subscribed_count,
                models.Subscribe.is_task == False,
                # models.Subscribe.id.not_in(completed_task_ids) if completed_task_ids else True
            )
            .limit(limit)
            .offset(offset)
        )
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def delete_subscribe(self, sub_id: int):
        sub = await self.get_subscribe(sub_id)
        if sub:
            await self.session.delete(sub)
            await self.session.commit()
            return True
        return False

    async def get_by_urls(self, urls: list[str]) -> list[models.Subscribe]:
        """Вернуть только те подписки, у которых url из списка"""
        if not urls:
            return []

        query = select(models.Subscribe).where(
            models.Subscribe.url.in_(urls),
            models.Subscribe.status == True
        )

        result = await self.session.execute(query)
        return result.scalars().all()    
