from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.database import models


class PromocodeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_promocode(self, **kwargs):
        promocode = models.Promocode(**kwargs)
        self.session.add(promocode)
        await self.session.commit()
        await self.session.refresh(promocode)
        return promocode

    async def get_promocode_by_code(self, code: str):
        result = await self.session.execute(select(models.Promocode).where(models.Promocode.code == code))
        return result.scalar_one_or_none()

    async def get_promocode(self, promocode_id: str):
        result = await self.session.execute(select(models.Promocode).where(models.Promocode.id == promocode_id))
        return result.scalar_one_or_none()

    async def get_all_promocodes(self, count: bool = False):
        query = select(func.count()).select_from(models.Promocode) if count else select(models.Promocode)
        result = await self.session.execute(query)
        return result.scalar() if count else result.scalars().all()

    async def update_promocode(self, promocode_id: int, **kwargs):
        promocode = await self.get_promocode(promocode_id)
        if not promocode:
            return None
        
        for key, value in kwargs.items():
            setattr(promocode, key, value)
        
        await self.session.commit()
        await self.session.refresh(promocode)
        return promocode

    async def delete_promocode(self, promo_id: int):
        promocode = await self.get_promocode(promo_id)
        if promocode:
            await self.session.delete(promocode)
            await self.session.commit()
            return True
        return False
