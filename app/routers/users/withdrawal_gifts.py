from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from app.keyboards import inline
import config

from aiogram import F, Router
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from app.routers.start import send_main_menu
from app.filters import IsPrivate, ReferralFilter
from app import keyboards as kb
from app.templates import texts
from app.database import db
from app.database.models.user import User
from app.database.repositories import UserRepository
from app.utils.utils import get_gifts, gifts_dir


withdrawal_user_gifts_router = Router(name='withdrawal_user_gifts_router')

@withdrawal_user_gifts_router.callback_query(F.data=='withdrawal', IsPrivate())
async def withdrawal_gifts_get_gifts(call: types.CallbackQuery, state: FSMContext, user: User):
    with suppress(TelegramBadRequest, TelegramForbiddenError):
        await call.message.edit_media(
            media=types.InputMediaPhoto(
                media=config.WITHDRAWAL_MAIN_MENU_ID,
            )
        )
        uid = user.user_id
        await call.message.edit_caption(
            caption=texts.withdrawal_menu_message.format(
                round(user.balance, 2),
                config.MAIN_CHANNEL_URL,
                f'<a href="tg://user?id={uid}">{uid} (Вы)</a>'
            ),
            reply_markup=inline.withdrawal_menu_kb()
        )
        return
    return await send_main_menu(call.message)

@withdrawal_user_gifts_router.callback_query(F.data=='withdrawal_change_user', IsPrivate(), ReferralFilter())
async def withdrawal_change_usser(call: types.CallbackQuery, state: FSMContext, user: User):
    await state.set_state('get_new_recevier')
    await call.message.edit_caption(
        reply_markup=inline.back_kb(
            calldata='main_menu',
            text='⬅️ В главное меню'
        ),
        caption=texts.change_receiver
    )
    
@withdrawal_user_gifts_router.message(StateFilter('get_new_recevier'), IsPrivate(), ReferralFilter())
async def get_new_user(message: types.Message, state: FSMContext, user: User):

    async with db.get_session() as session:
        user_repo = UserRepository(session)

        if not message.text.isdigit() or not await user_repo.get_user(user_id=int(message.text)):
            await state.clear()
            await message.answer('❌ Пользователь не найден!')
            return await send_main_menu(message)

    await state.set_data({'receiver': int(message.text)})
    receiver = int(message.text)

    await message.answer_photo(
        photo=config.WITHDRAWAL_MAIN_MENU_ID,
        caption=texts.withdrawal_menu_message.format(
            round(user.balance, 2),
            config.MAIN_CHANNEL_URL,
            f'<a href="tg://user?id={receiver}">{str(receiver) + " (Вы)" if receiver == user.user_id else str(receiver)}</a>'
        ),
        reply_markup=inline.withdrawal_menu_kb()
    )
    

@withdrawal_user_gifts_router.callback_query(F.data=='withdrawal_gifts', IsPrivate())
async def withdrawal_gifts_get_gifts(call: types.CallbackQuery, state: FSMContext, user: User):
    receiver = (await state.get_data()).get('receiver', call.from_user.id)

    gifts = await get_gifts()
    message = call.message
    total_count = gifts[0]['total']
    gifts = gifts[1]['gifts']
    
    if not gifts:
        return await call.answer(
            texts.gifts_empty_message,
            show_alert=True
        )
    await call.message.delete()
    await call.message.answer_photo(
        photo=types.FSInputFile(f'{gifts_dir}/{gifts[0]["gift_id"]}.jpg'),
        caption=texts.gift_caption.format(
            total_count,
            gifts[0]['gifts_count'] or '∞',
            gifts[0]['gift_star_count'],
            round(user.balance, 2),
            (await message.bot.get_me()).username,
            message.from_user.id,
            f'<a href="tg://user?id={receiver}">{str(receiver) + " (Вы)" if receiver == user.user_id else str(receiver)}</a>'
        ),
        reply_markup=kb.inline.gifts_swiper(
            id1=total_count,
            id2=2,
            gift_id=gifts[0]['gift_id'],
            cost=gifts[0]['gift_star_count'],
        )
    )

@withdrawal_user_gifts_router.callback_query(F.data.startswith('gifts:'), IsPrivate())
async def gifts_swiper_main_menu(call: types.CallbackQuery, state: FSMContext, user: User):
    
    receiver = (await state.get_data()).get('receiver', call.from_user.id)

    raw = int(call.data.split(':')[-1])
    data = await get_gifts()

    total_count = data[0]['total']
    gifts = data[1]['gifts']

    for gift in gifts:
        if gift['id'] == int(raw):
            select_gift = gift
            
    with suppress(TelegramBadRequest):
        await call.message.delete()

    await call.message.answer_photo(
        photo=types.FSInputFile(f'gifts/{select_gift["gift_id"]}.jpg'),
        caption=texts.gift_caption.format(
            total_count,
            select_gift['gifts_count'] or '∞',
            select_gift['gift_star_count'],
            round(user.balance, 2),
            (await call.message.bot.get_me()).username,
            call.message.from_user.id,
            f'<a href="tg://user?id={receiver}">{str(receiver) + " (Вы)" if receiver == user.user_id else str(receiver)}</a>'
        ),
        reply_markup=kb.inline.gifts_swiper(
            id1=select_gift['id'] - 1 if raw != 1 else total_count,
            id2=select_gift['id'] + 1 if raw != total_count else 1,
            gift_id=select_gift['gift_id'],
            cost=select_gift['gift_star_count']
        )
    )


@withdrawal_user_gifts_router.callback_query(F.data=='withdrawal_premium', IsPrivate(), ReferralFilter())
async def withdrawal_tg_premium(call: types.CallbackQuery, state: FSMContext, user: User):
    receiver = (await state.get_data()).get('receiver', user.user_id)
    tg_prem_cost = 1700
    await state.clear()

    if tg_prem_cost > user.balance:
        return await call.answer(texts.not_enough_money_withdrawal, show_alert=True)

    async with db.get_session() as session:
        user_repo = UserRepository(session)
        await user_repo.update_user(user_id=user.user_id, balance=user.balance - tg_prem_cost)
        user = await user_repo.get_user(user_id=int(receiver))
        referral_stats = await user_repo.get_referral_stats(user.user_id)

    await call.message.delete()
    await call.message.answer(
        text=texts.withdrawal_send_to_moderation,
    )
    avg_time_str = "нет данных"
    if referral_stats['avg_time_between']:
        avg_seconds = referral_stats['avg_time_between']
        if avg_seconds < 60:
            avg_time_str = f"{int(avg_seconds)} сек"
        elif avg_seconds < 3600:
            avg_time_str = f"{int(avg_seconds / 60)} мин"
        else:
            avg_time_str = f"{int(avg_seconds / 3600)} час"

    with suppress(TelegramBadRequest):
        await call.message.bot.send_message(
            chat_id=config.MODERTAION_CHAT_ID,
            text=texts.withdrawal_stars_ticket.format(
                user_id=user.user_id,
                user_fullname=user.user_fullname,
                amount=tg_prem_cost,
                username=user.user_name,
                total_referrals=referral_stats['total_referrals'],
                total_active=referral_stats['total_active'],
                total_alive=referral_stats['total_alive'],
                avg_time_str=avg_time_str
            ),
            reply_markup=kb.inline.withdrawal_moderation_gifts_kb(
                user_id=user.user_id,
                amount=tg_prem_cost,
                gift_id=-1
            )
        )
    return await send_main_menu(call.message)

@withdrawal_user_gifts_router.callback_query(F.data.startswith('buy_gift:'), IsPrivate(), ReferralFilter())
async def buy_gift_func(call: types.CallbackQuery, state: FSMContext, user: User):
    receiver = (await state.get_data()).get('receiver', user.user_id)

    await state.clear()

    gift_id = call.data.split(':')[1]
    gift_cost = int(call.data.split(':')[2])

    if gift_cost > user.balance:
        return await call.answer(texts.not_enough_money_withdrawal)

    async with db.get_session() as session:
        user_repo = UserRepository(session)
        await user_repo.update_user(user_id=user.user_id, balance=user.balance-gift_cost)
        user = await user_repo.get_user(user_id=int(receiver))
        referral_stats = await user_repo.get_referral_stats(user.user_id)

    avg_time_str = "нет данных"
    if referral_stats['avg_time_between']:
        avg_seconds = referral_stats['avg_time_between']
        if avg_seconds < 60:
            avg_time_str = f"{int(avg_seconds)} сек"
        elif avg_seconds < 3600:
            avg_time_str = f"{int(avg_seconds / 60)} мин"
        else:
            avg_time_str = f"{int(avg_seconds / 3600)} час"

    try:
        await call.message.delete()
    except:
        ...
    await call.message.answer(
        text=texts.withdrawal_send_to_moderation,
    )

    with suppress(TelegramBadRequest):
        await call.message.bot.send_message(
            chat_id=config.MODERTAION_CHAT_ID,
            text=texts.withdrawal_stars_ticket.format(
                user_id=user.user_id,
                user_fullname=user.user_fullname,
                amount=gift_cost,
                username=user.user_name,
                total_referrals=referral_stats['total_referrals'],
                total_active=referral_stats['total_active'],
                total_alive=referral_stats['total_alive'],
                avg_time_str=avg_time_str
            ),
            reply_markup=kb.inline.withdrawal_moderation_gifts_kb(
                user_id=user.user_id,
                amount=gift_cost,
                gift_id=gift_id
            )
        )
    return await send_main_menu(call.message)