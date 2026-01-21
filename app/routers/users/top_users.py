import config

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from contextlib import suppress

from app.routers.start import send_main_menu
from app.utils.misc_function import get_time_now
from app.templates.button_texts import users_get_top_button
from app.templates.texts import (
    top_users_message, top_users_period_today, 
    top_users_period_all, top_users_empty, top_users_item
)
from app.filters import IsPrivate
from app.keyboards.inline import top_users_kb
from app.database.repositories.user_repo import UserRepository
from app.database import db

top_users_router = Router(name='top_users_router')

async def get_top_users(period: str = 'today') -> str:
    async with db.get_session() as session:
        user_repo = UserRepository(session)
        top_users = await user_repo.get_top_referrals(period)

    if not top_users:
        return top_users_empty

    result = []
    for i, (name, count) in enumerate(top_users, 1):
        result.append(top_users_item.format(
            pos=i,
            name=name,
            count=count
        ))

    return "\n".join(result)

@top_users_router.message(F.text==users_get_top_button, IsPrivate())
async def show_top_users(message: types.Message, state: FSMContext):
    await state.clear()
    
    async with db.get_session() as session:
        user_repo = UserRepository(session)
        position, refs_count = await user_repo.get_user_position(message.from_user.id, 'today')
    
    top_users_text = await get_top_users('today')
    await message.answer_photo(
        photo=types.FSInputFile(str(config.MEDIA_DIR / 'raitings.png')),
        caption=top_users_message.format(
            period=top_users_period_today,
            top_users=top_users_text,
            user_position=position,
            user_refs=refs_count
        ),
        reply_markup=top_users_kb(),
        parse_mode="HTML"
    )

@top_users_router.callback_query(F.data.startswith('top_users:'))
async def process_top_users_period(callback: types.CallbackQuery):
    period = callback.data.split(':')[1]
    
    async with db.get_session() as session:
        user_repo = UserRepository(session)
        position, refs_count = await user_repo.get_user_position(callback.from_user.id, period)
    
    top_users_text = await get_top_users(period)
    period_text = top_users_period_today if period == 'today' else top_users_period_all
    
    with suppress(TelegramBadRequest):
        await callback.message.edit_media(
            media=types.InputMediaPhoto(
                media=config.TOP_MAIN_MENU_ID
            )
        )
        await callback.message.edit_caption(
            caption=top_users_message.format(
                period=period_text,
                top_users=top_users_text,
                user_position=position,
                user_refs=refs_count
            ),
            reply_markup=top_users_kb(),
            parse_mode="HTML"
        )
        return
    return await send_main_menu(callback.message)