from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import models


class GiftIssueRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def increment_user_gifts(self, user_id: int) -> int:
        result = await self.session.execute(
            select(models.GiftIssue).where(models.GiftIssue.user_id == user_id)
        )
        issue = result.scalar_one_or_none()
        if issue is None:
            issue = models.GiftIssue(user_id=user_id, total_count=1)
            self.session.add(issue)
        else:
            issue.total_count += 1
            self.session.add(issue)

        await self.session.commit()
        await self.session.refresh(issue)
        return issue.total_count

    async def get_user_gift_count(self, user_id: int) -> int:
        result = await self.session.execute(
            select(models.GiftIssue.total_count).where(models.GiftIssue.user_id == user_id)
        )
        count = result.scalar_one_or_none()
        return count or 0
