from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from app.utils.utils import get_admins

class IsAdmin(BaseFilter):
    def __init__(self,):
        self.admin_ids = get_admins()

    async def __call__(self, message: Message | CallbackQuery) -> bool:
        return int(message.from_user.id) in self.admin_ids