from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql.expression import delete

from app.database import models

class AdvertHistoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_advert_history(self, **kwargs):
        advert_history = models.AdvertHistory(**kwargs)
        self.session.add(advert_history)
        await self.session.commit()
        await self.session.refresh(advert_history)
        return advert_history

    async def delete_by_user_id(self, user_id: int) -> int:
        result = await self.session.execute(
            delete(models.AdvertHistory).where(models.AdvertHistory.user_id == user_id)
        )
        await self.session.commit()
        return result.rowcount or 0

