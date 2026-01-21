from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest
import config

from aiogram import F, Router
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from app.routers.start import send_main_menu
from app.filters import IsPrivate
from app.keyboards.inline import cancel_kb, withdrawal_moderation_kb
from app.templates import texts
from app.database import db
from app.database.models.user import User
from app.database.repositories import UserRepository
from app.templates.button_texts import users_withrawal_stars_button
from app.states.withdrawal import WithdrawalState


withdrawal_user_router = Router(name='withdrawal_user_router')


@withdrawal_user_router.message(F.text==users_withrawal_stars_button)
async def withdrawal_via_stars(message: types.Message, state: FSMContext):
    await state.clear()

    await message.answer_photo(
        photo=types.FSInputFile('app/static/withdrawal.jpg'),
        caption=texts.withdrawal_user_text,
        reply_markup=cancel_kb()
    )

    return await state.set_state(WithdrawalState.get_amount)

@withdrawal_user_router.message(
    IsPrivate(),
    StateFilter(WithdrawalState.get_amount)
)
async def withdrawal_get_amount(message: types.Message, state: FSMContext, user: User):
    await state.clear()

    try:
        amount = int(message.text)
    except ValueError:
        return await message.answer(
            text=texts.error_message,
            reply_markup=cancel_kb()
        )

    if amount < 50:
        return await message.answer(
            text=texts.withdrawal_min_amount_error,
            reply_markup=cancel_kb()
        )

    if user.balance < amount:
        return await message.answer(
            text=texts.not_enough_money_withdrawal,
            reply_markup=cancel_kb()
        )

    async with db.get_session() as session:
        user_repo = UserRepository(session)
        await user_repo.update_user(user_id=user.user_id, balance=user.balance-amount)

    await message.answer(
        text=texts.withdrawal_send_to_moderation,
    )

    with suppress(TelegramBadRequest):
        await message.bot.send_message(
            chat_id=config.MODERTAION_CHAT_ID,
            text=texts.withdrawal_stars_ticket.format(
                user_id=user.user_id,
                user_fullname=user.user_fullname,
                amount=amount,
                username=user.user_name
            ),
            reply_markup=withdrawal_moderation_kb(
                user_id=user.user_id,
                amount=amount
            )
        )
        return
    return await send_main_menu(message)