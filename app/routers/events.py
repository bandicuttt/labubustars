from contextlib import suppress
from re import A
from aiogram import types, Router, F
from aiogram.enums.chat_member_status import ChatMemberStatus
from aiogram.enums.chat_type import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.filters import IsPrivate
from app.database.models import User
from app.database import repositories, db
from app.templates import texts
from app.routers.start import send_main_menu
from app.utils.closed_channel_requests import save_closed_channel_request
from app.utils.utils import get_admins
from app.utils.misc_function import get_time_now
from app.logger import logger

event_chat_router = Router(name='event_chat_router')


@event_chat_router.my_chat_member()
async def start_menu(message: types.ChatMemberUpdated, user: User | None):
    user_status = message.new_chat_member.status
    chat_type = message.chat.type
    user_id = message.from_user.id
    chat_id = message.chat.id
    member_id = message.new_chat_member.user.id
    bot_id = message.bot.id

    if chat_type == ChatType.PRIVATE:
        if user_status == ChatMemberStatus.KICKED:
            async with db.get_session() as session:
                user_repo = repositories.UserRepository(session)
                await user_repo.update_user(
                    user_id=user_id,
                    block_date=get_time_now()
                )
        return

    if not member_id == bot_id:
        return

    async with db.get_session() as session:
        chat_repo = repositories.UserChatRepository(session)

        chat = await chat_repo.get_chat(chat_id=chat_id)

        if chat_type == ChatType.GROUP and user_status == ChatMemberStatus.LEFT:
            return await chat_repo.update_chat(chat_id=chat_id, block_date=get_time_now())

        if user_status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
            return

        bot_username = (await message.bot.get_me()).username

        if chat_type == ChatType.SUPERGROUP:
            return
            await message.answer_photo(
                photo=types.FSInputFile('app/templates/stars_menu.jpg'),
                caption=texts.user_new_chat.format(
                    bot_username=bot_username
                )
            )

        if chat_type == ChatType.GROUP:
            return
            await message.answer_photo(
                photo=types.FSInputFile('app/templates/stars_menu.jpg'),
                caption=texts.user_new_chat.format(
                    bot_username=bot_username
                )
            )

        if not chat:
            return await chat_repo.create_chat(
                user_id=user_id if user else get_admins()[0],
                chat_id=chat_id
            )
        return await chat_repo.update_chat(chat_id=chat_id, block_date=None)


@event_chat_router.message(F.new_chat_members)
async def new_chat_members(message: types.Message):
    return
    new_member = message.new_chat_members[0]

    if new_member.id == message.bot.id:
        return

    await message.answer(
        text=texts.user_chat_new_member
    )


@event_chat_router.message(F.left_chat_member)
async def new_chat_members(message: types.Message):
    return
    left_member = message.left_chat_member

    if left_member.id == message.bot.id:
        return

    await message.answer(
        text=texts.user_chat_left_member
    )


@event_chat_router.chat_join_request()
async def on_chat_join_request(request: types.ChatJoinRequest):
    if request.chat.type != ChatType.CHANNEL:
        return

    await save_closed_channel_request(
        chat_id=request.chat.id,
        user_id=request.from_user.id,
    )


@event_chat_router.callback_query(F.data.startswith('check_subscribe'))
async def check_subscribe(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer(text=texts.subscribe_done_message)
    await send_main_menu(call.message)


@event_chat_router.error()
async def forbidden_handler(update: types.Update, exception: Exception):
    if isinstance(exception, TelegramForbiddenError, TelegramBadRequest):
        user_id = None
        if update.message:
            user_id = update.message.from_user.id
        elif update.callback_query:
            user_id = update.callback_query.from_user.id

        async with db.get_session() as session:
            user_repo = repositories.UserRepository(session)
            await user_repo.update_user(
                user_id=user_id,
                block_date=get_time_now()
            )
        return True

    logger.error(
        f"Необработанная ошибка при обработке update={update}",
        exc_info=exception
    )
    return False


@event_chat_router.message(IsPrivate())
async def main_missed(message: types.Message):
    with suppress(TelegramBadRequest):
        await message.delete()
    await send_main_menu(message)


@event_chat_router.callback_query(IsPrivate())
async def main_missed(call: types.CallbackQuery):
    try:
        await call.message.delete()
    except:
        ...
    await send_main_menu(call.message)
