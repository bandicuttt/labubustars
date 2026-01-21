from aiogram import Dispatcher

from .start import start_router
from .admins import get_admin_routers
from .users import get_user_routers
from .errors import errors_router
from .events import event_chat_router


async def reg_handlers(dp: Dispatcher):
    dp.include_router(start_router)
    dp.include_routers(*get_admin_routers())
    dp.include_routers(*get_user_routers())
    dp.include_router(errors_router)
    dp.include_router(event_chat_router)
    