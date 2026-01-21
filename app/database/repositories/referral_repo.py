from typing import Optional, List

from sqlalchemy import delete, select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import query

from app.database.models import Referral, User


class ReferralRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_referral(
        self,
        ref: str,
        price: float,
        admin_url: str,
        total_visits: int = 0
    ) -> Referral:
        """Create a new referral"""
        referral = Referral(
            ref=ref,
            price=price,
            admin_url=admin_url,
            total_visits=total_visits
        )
        self.session.add(referral)
        await self.session.commit()
        return referral

    async def get_referral_by_ref(self, ref: str) -> Optional[Referral]:
        """Get referral by ref code"""
        query = select(Referral).where(Referral.ref == ref)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def is_ref_exists(self, ref: str) -> bool:
        """
        Check if ref exists in either Referral model or User model
        Returns True if ref exists, False otherwise
        """
        # Check in Referral model
        referral_query = select(Referral).where(Referral.ref == ref)
        referral_result = await self.session.execute(referral_query)
        if referral_result.scalar_one_or_none():
            return True

        # Check in User model
        user_query = select(User).where(User.ref == ref)
        user_result = await self.session.execute(user_query)
        if user_result.scalar_one_or_none():
            return True

        return False

    async def get_referrals(self, offset: int = 0, limit: int = 5) -> List[Referral]:
        """Get paginated list of referrals"""
        query = select(Referral).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_referral(
        self,
        ref: str,
        **kwargs
    ) -> Optional[Referral]:
        """Update referral fields"""
        query = update(Referral).where(Referral.ref == ref).values(**kwargs)
        await self.session.execute(query)
        await self.session.commit()
        return await self.get_referral_by_ref(ref)

    async def increment_uniq_visits(self, ref: str) -> Optional[Referral]:
        """Increment total_visits counter for referral"""
        referral = await self.get_referral_by_ref(ref)
        if referral:
            return await self.update_referral(
                ref=ref,
                total_uniq_visits=referral.total_uniq_visits + 1
            )
        return None

    async def increment_total_visits(self, ref: str) -> Optional[Referral]:
        """Increment total_visits counter for referral"""
        referral = await self.get_referral_by_ref(ref)
        if referral:
            return await self.update_referral(
                ref=ref,
                total_visits=referral.total_visits + 1
            )
        return None

    async def delete_referral(self, ref: str):
       query = delete(Referral).where(Referral.ref==ref)
       await self.session.execute(query)
       await self.session.commit()

