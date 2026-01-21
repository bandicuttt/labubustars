from typing import Union

from aiogram.enums import ChatType
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery


class IsPrivate(BaseFilter):
    async def __call__(self, obj: Message | CallbackQuery) -> bool:
        if isinstance(obj, CallbackQuery):
            return obj.message.chat.type == ChatType.PRIVATE
        return obj.chat.type == ChatType.PRIVATE
