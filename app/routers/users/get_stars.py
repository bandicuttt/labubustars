from contextlib import suppress

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext

from app.database import db
from app.database.models import User
from app.database.repositories import UserRepository
from app.filters import IsPrivate
from app.keyboards.inline import get_stars_kb, old_friends_kb, old_friends_list_kb, insturction_kb
from app.templates.texts import get_stars_text_message, old_friends, instruction_text, old_frineds_list_message
from app.utils.utils import send_main_menu_util
from config import BOT_USERNAME, GET_STARS_MENU_ID, INSTRUCTION_MENU_ID, OLD_FRIENDS_MAIN_MENU_ID

get_stars_router = Router(name='get_stars_router')


@get_stars_router.callback_query(F.data=='get_stars', IsPrivate())
async def get_stars(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()

    bot_username = BOT_USERNAME

    await call.message.answer_photo(
        photo=GET_STARS_MENU_ID,
        reply_markup=get_stars_kb(bot_username, call.from_user.id),
        caption=get_stars_text_message.format(
            user_ref=f'https://t.me/{bot_username}?start={call.from_user.id}'
        )
    )

@get_stars_router.callback_query(F.data=='old_friends', IsPrivate())
async def old_friends_menu(call: types.CallbackQuery, state: FSMContext, user: User):
    await call.message.edit_media(
        media=types.InputMediaPhoto(
            media=OLD_FRIENDS_MAIN_MENU_ID
        )
    )

    await call.message.edit_caption(
        caption=old_friends.format(
        ),
        reply_markup=old_friends_kb(
            BOT_USERNAME,
            user.user_id
        )
    )

@get_stars_router.callback_query(F.data=='get_inactive_users', IsPrivate())
async def get_inactive_users(call: types.CallbackQuery, state: FSMContext, user: User):
    async with db.get_session() as session:
        user_repo = UserRepository(session)
        inactive_users, repeat_count = await user_repo.get_inactive_users(referrer_user_id=str(user.user_id))

    if not inactive_users:
        return await call.answer('У вас нет не активных друзей ✅', show_alert=True)

    text = old_frineds_list_message.format(inactive_users)
    bot_username = BOT_USERNAME
    try:
        return await call.message.edit_caption(
            caption=text,
            reply_markup=old_friends_list_kb(bot_username, user.user_id)
        )
    except:
        # ту мач юзеров
        await call.message.delete()
        await call.message.answer(text, old_friends_list_kb(bot_username, user.user_id, True))
        await send_main_menu_util(call.message)


@get_stars_router.callback_query(F.data=='instruction', IsPrivate())
async def instruction_menu(call: types.CallbackQuery, state: FSMContext, user: User):
    with suppress(TelegramBadRequest, TelegramForbiddenError):
        await call.message.edit_media(
            media=types.InputMediaPhoto(
                media=INSTRUCTION_MENU_ID
            )
        )
        await call.message.edit_caption(
            caption=instruction_text,
            reply_markup=insturction_kb()
        )
        return
    
    return await send_main_menu_util(call.message)
