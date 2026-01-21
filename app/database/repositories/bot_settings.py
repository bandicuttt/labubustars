from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models.settings import Settings


class SettingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str, default=None) -> str | None:
        result = await self.session.execute(
            select(Settings.value).where(Settings.key == key)
        )
        value = result.scalar_one_or_none()
        return value if value is not None else default

    async def set(self, key: str, value: str):
        # ищем запись
        result = await self.session.execute(
            select(Settings).where(Settings.key == key)
        )
        row: Settings | None = result.scalar_one_or_none()

        if row:
            row.value = value
        else:
            row = Settings(key=key, value=value)
            self.session.add(row)

        await self.session.commit()

