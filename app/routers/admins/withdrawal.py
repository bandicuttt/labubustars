from aiogram import F, Router
from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from app.filters.admin import IsAdmin
from app.keyboards.inline import admin_moderation_main_kb, cancel_kb

from app.database import db
from app.database.models.user import User
from app.database.repositories import UserRepository
from app.templates import texts

import config
from loader import bot

withdrawal_admin_router = Router(name='withdrawal_admin_router')


@withdrawal_admin_router.callback_query(F.data.startswith('withrawal_gift:'), IsAdmin())
async def withdrawal_action(call: types.CallbackQuery, state: FSMContext, user: User):
    await state.clear()

    action = call.data.split(':')[1]
    user_id = int(call.data.split(':')[2])
    gift_id = call.data.split(':')[3]
    amount = int(call.data.split(':')[4])

    if action == 'discard':
        async with db.get_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_user(user_id=user_id)
            await user_repo.update_user(user_id=user_id, balance=user.balance+amount)

        return await bot.send_message(
            chat_id=user_id,
            text=texts.withdrawal_discard_error_message.format(
                support=config.SUPPORT_USERNAME
            )
        )

    if action == 'accept':
        try:
            await bot.send_gift(
                user_id=user_id,
                gift_id=gift_id,
                text=texts.gift_caption_send.format(
                    bot_username=config.BOT_USERNAME
                )
            )
        except TelegramBadRequest:
            return await call.message.reply(text=texts.withdrawal_gifts_error)

        await call.message.reply(text=texts.withdrawal_auto_success_admin_message)

        await call.message.edit_reply_markup(
            reply_markup=admin_moderation_main_kb(is_accept=False if action == 'discard' else True)
        )

        await bot.send_message(
            chat_id=config.REVIEWS_CHANNEL_ID,
            text=texts.withdrawal_chat_success_admin_message.format(
                user_id,
                amount,
                config.MAIN_CHANNEL_URL,
                config.MAIN_CHAT_URL,
                f'https://t.me/{config.BOT_USERNAME}'
            )
        )

        return await bot.send_message(
            chat_id=user_id,
            text=texts.withdrawal_success_user_message.format(
                support=config.SUPPORT_USERNAME
            )
        )

@withdrawal_admin_router.callback_query(F.data.startswith('withrawal_admin:'), IsAdmin())
async def withdrawal_action(call: types.CallbackQuery, state: FSMContext, user: User):
    await state.clear()

    action = call.data.split(':')[1]
    user_id = int(call.data.split(':')[2])
    amount = int(call.data.split(':')[3])

    await call.message.edit_reply_markup(
        reply_markup=admin_moderation_main_kb(is_accept=False if action == 'discard' else True)
    )

    if action == 'discard':
        async with db.get_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_user(user_id=user_id)
            await user_repo.update_user(user_id=user_id, balance=user.balance+amount)

        return await bot.send_message(
            chat_id=user_id,
            text=texts.withdrawal_discard_error_message.format(
                support=config.SUPPORT_USERNAME
            )
        )

    if action == 'accept':

        await call.message.reply(
            text=texts.withdrawal_stars_message,
            reply_markup=cancel_kb()
        )

        await bot.send_message(
            chat_id=user_id,
            text=texts.withdrawal_success_auto_message
        )