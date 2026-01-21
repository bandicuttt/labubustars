from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.database import models

class UserChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_chat(self, **kwargs):
        chat = models.UserChat(**kwargs)
        self.session.add(chat)
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def get_chat(self, chat_id: int):
        result = await self.session.execute(select(models.UserChat).where(models.UserChat.chat_id == chat_id))
        return result.scalar_one_or_none()

    async def get_all_chats(self):
        result = await self.session.execute(select(models.UserChat))
        return result.scalars().all()

    async def update_chat(self, chat_id: int, **kwargs):
        chat = await self.get_chat(chat_id)
        for key, value in kwargs.items():
            setattr(chat, key, value)
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def get_count_chats_offsets(self, offset1: str, offset2: str, **kwargs):
        query = select(func.count()).select_from(models.UserChat)

        conditions = [
            models.UserChat.created_at > offset2,
            models.UserChat.created_at < offset1
        ]

        for key, value in kwargs.items():
            if hasattr(models.UserChat, key):
                if key == 'block_date' and value:
                    conditions.append(models.UserChat.block_date.isnot(None))
                else:
                    conditions.append(getattr(models.UserChat, key) == value)

        query = query.where(*conditions)

        result = await self.session.execute(query)
        return result.scalar()
    
    async def delete_chat(self, chat_id: int):
        chat = await self.get_chat(chat_id)
        if chat:
            await self.session.delete(chat)
            await self.session.commit()
            return True
        return False