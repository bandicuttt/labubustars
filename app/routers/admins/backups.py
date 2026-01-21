from app import templates
from app.filters import IsAdmin
from app.database import repositories, db

from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from contextlib import suppress
from datetime import datetime

from app.utils.misc_function import get_time_now


admin_backup_router = Router(name='admin_backup_router')

@admin_backup_router.message(F.text==templates.button_texts.admin_backup_button, IsAdmin())
async def start_menu(message: types.Message, state: FSMContext):
    async with db.get_session() as session:
        user_repo = repositories.UserRepository(session)
        dump_date = get_time_now().strftime("%Y.%m.%d")

        for file in await user_repo.create_dump():
            with suppress(TelegramBadRequest, TelegramNetworkError):
                await message.answer_document(
                    document=types.FSInputFile(path=file),
                    caption=dump_date
                )