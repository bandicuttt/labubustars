import config

from aiogram import F, Router
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from app.filters import IsPrivate
from app.keyboards.inline import cancel_kb, top_up_balance_kb
from app.templates import texts
from app.states.top_up_balance import TopUpBalanceState
from app.database import db
from app.database.models.user import User
from app.database.repositories import UserRepository

from loader import bot


top_up_balance_router = Router(name='top_up_balance_router')

@top_up_balance_router.callback_query(
    IsPrivate(),
    StateFilter('*'),
    F.data.startswith('top_up_balance')
)
async def top_up_balance(call: types.CallbackQuery, state: FSMContext):
    await state.clear()

    await call.message.edit_caption(
        caption=texts.top_up_balance_message_get_amount,
        reply_markup=cancel_kb()
    )
    await state.set_state(TopUpBalanceState.get_amount)

@top_up_balance_router.message(
    IsPrivate(),
    StateFilter(TopUpBalanceState.get_amount)
)
async def get_amount(message: types.Message, state: FSMContext):
    await state.clear()

    try:
        amount = int(message.text)
    except ValueError:
        amount = 100

    pay_url = await bot.create_invoice_link(
        title=f'Пополнение баланса бота @{config.BOT_USERNAME}',
        description=config.BOT_USERNAME,
        payload="bot_support",
        currency="XTR",
        provider_token="",
        prices=[types.LabeledPrice(label="XTR", amount=amount)]  
    )

    await message.answer_photo(
        photo=config.GAMES_MENU_ID,
        caption=texts.top_up_balance_message,
        reply_markup=top_up_balance_kb(pay_url=pay_url)
    )

@top_up_balance_router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@top_up_balance_router.message(F.successful_payment)
async def _(message: types.Message, state: FSMContext, user: User):
    amount = message.successful_payment.total_amount
    
    await message.answer('🎉')

    await message.answer(
        text=texts.successful_payment_message,
    )
    
    async with db.get_session() as session:
        user_repo = UserRepository(session)
        await user_repo.update_user(user_id=user.user_id, balance=user.balance+amount)

    