from loader import bot
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware, types
from aiogram.types import Update, Message
from aiogram.exceptions import TelegramBadRequest


class ExitMiddleware(BaseMiddleware):
    async def __call__(
        self, 
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        event_user: Optional[types.User] = data.get("event_from_user")
        event_chat: Optional[types.Chat] = data.get("event_chat")
        temp: int | None = data.get('temp')

        if not temp:
            return await handler(event, data)

        try:
            await bot.delete_message(
                chat_id=event_user.id,
                message_id=temp
            )
        except TelegramBadRequest:
            ...
        finally:
            return await handler(event, data)
        