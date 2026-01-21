from re import A
from aiogram.filters import StateFilter
from sqlalchemy import exc
from app import templates
from app.filters import IsAdmin, IsPrivate
from app import keyboards as kb
from app import templates
from app.database import db, redis_pool
from app.database.repositories import UserRepository, ReferralRepository
from app.utils.stats import audit_stat
from app.utils.utils import get_times, get_ref_stat_new, get_time_now
from app.states.referrals import ReferralState
from app.database.models import User

from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext

admin_referral_router = Router(name='admin_referral_router')


@admin_referral_router.message(F.text == templates.button_texts.admin_referrals_button, IsAdmin())
async def start_menu(message: types.Message, state: FSMContext):
    await state.clear()
    async with db.get_session() as session:
        user_repo = UserRepository(session)
        referrals = await user_repo.get_unique_refs()

    await message.answer(
        text=templates.texts.admin_referrals_message,
        reply_markup=kb.inline.admin_referrals(
            referrals=referrals,
            raw=0
        )
    )


@admin_referral_router.message(F.text.startswith('/ref_'), IsPrivate())
async def get_ref_stat_func(message: types.Message, state: FSMContext, user: User):
    try:
        ref = message.text.split('_')[1]
    except IndexError:
        return await message.answer(
            text=templates.texts.ref_error
        )

    async with db.get_session() as session:
        ref_repo = ReferralRepository(session)
        ref_info = await ref_repo.get_referral_by_ref(ref)

    if not ref_info:
        return await message.reply('❌')

    if '@' + message.from_user.username not in ref_info.admin_url:
        return await message.reply('❌')

    async with redis_pool.get_connection() as con:
        # Получаем общее количество уникальных пользователей
        total_unique = await con.get(f'unique:{ref_info.ref}')
        total_unique = int(total_unique.decode('utf-8')) if total_unique else 0

        # Получаем уникальных пользователей за сегодня
        today = get_time_now().strftime("%Y-%m-%d")
        daily_unique = await con.get(f'daily_unique:{ref_info.ref}:{today}')
        daily_unique = int(daily_unique.decode('utf-8')) if daily_unique else 0

        # Общие клики (все переходы)
        total_clicks = await con.get(f'total:{ref_info.ref}')
        total_clicks = int(total_clicks.decode('utf-8')) if total_clicks else ref_info.total_visits 

        # Клики за сегодня
        daily_clicks = await con.get(f'daily:{ref_info.ref}:{today}')
        daily_clicks = int(daily_clicks.decode('utf-8')) if daily_clicks else 0

    data = await get_ref_stat_new(ref=ref)
    await message.answer_photo(
        photo=(types.FSInputFile(
            await audit_stat(
                today=get_times()[0],
                ref=ref
            )
        )),
        caption=templates.texts.admin_referral_stat_mew.format(
            **data,
            bot_username=(await message.bot.get_me()).username,
            ref=ref,
            admin=ref_info.admin_url,
            total_uniq_clicks=total_clicks,
            total_uniq_clicks_today=daily_clicks,
        ),
    )


@admin_referral_router.callback_query(F.data.startswith('referals:'), IsAdmin())
async def referrals_menu(call: types.CallbackQuery, state: FSMContext):
    action = call.data.split(':')[1]
    ref = call.data.split(':')[2]

    if action == 'create':
        await call.message.edit_text(
            text=templates.texts.admin_create_ref_message,
            reply_markup=kb.inline.cancel_kb()
        )
        return await state.set_state(ReferralState.get_ref)

    async with db.get_session() as session:
        ref_repo = ReferralRepository(session)
        ref_info = await ref_repo.get_referral_by_ref(ref=ref)

        if action == 'delete':
            await ref_repo.delete_referral(ref=ref)
            async with db.get_session() as session:
                user_repo = UserRepository(session)
                referrals = await user_repo.get_unique_refs()
            await call.message.delete()

            await call.message.answer(
                text=templates.texts.admin_referrals_message,
                reply_markup=kb.inline.admin_referrals(
                    referrals=referrals,
                    raw=0
                )
            )

        if action == 'get_stat':
            await call.message.delete()

            async with redis_pool.get_connection() as con:
                # Получаем общее количество уникальных пользователей
                total_unique = await con.get(f'unique:{ref_info.ref}')
                total_unique = int(total_unique.decode('utf-8')) if total_unique else 0

                # Получаем уникальных пользователей за сегодня
                today = get_time_now().strftime("%Y-%m-%d")
                daily_unique = await con.get(f'daily_unique:{ref_info.ref}:{today}')
                daily_unique = int(daily_unique.decode('utf-8')) if daily_unique else 0

                # Общие клики (все переходы)
                total_clicks = await con.get(f'total:{ref_info.ref}')
                total_clicks = int(total_clicks.decode('utf-8')) if total_clicks else ref_info.total_visits

                # Клики за сегодня
                daily_clicks = await con.get(f'daily:{ref_info.ref}:{today}')
                daily_clicks = int(daily_clicks.decode('utf-8')) if daily_clicks else 0

            data = await get_ref_stat_new(ref=ref)
            await call.message.answer_photo(
                photo=(types.FSInputFile(
                    await audit_stat(
                        today=get_times()[0],
                        ref=ref
                    )
                )),
                caption=templates.texts.admin_referral_stat_mew.format(
                    **data,
                    bot_username=(await call.message.bot.get_me()).username,
                    ref=ref,
                    admin=ref_info.admin_url,
                    total_uniq_clicks=total_clicks,
                    total_uniq_clicks_today=daily_clicks
                ),
                reply_markup=kb.inline.ref_admin_kb(ref)
            )


@admin_referral_router.message(StateFilter(ReferralState.get_ref), IsAdmin())
async def get_ref_name(message: types.Message, state: FSMContext):
    if not message.text.isascii() or not message.text.isalpha():
        return await message.answer(
            text=templates.texts.error_message,
            reply_markup=kb.inline.cancel_kb()
        )

    async with db.get_session() as session:
        referral_repo = ReferralRepository(session)
        if await referral_repo.is_ref_exists(message.text):
            return await message.answer(
                text=templates.texts.error_message,
                reply_markup=kb.inline.cancel_kb()
            )

    await state.update_data(ref=message.text)
    await state.set_state(ReferralState.get_price)
    await message.answer(
        text=templates.texts.admin_create_ref_price,
        reply_markup=kb.inline.cancel_kb()
    )


@admin_referral_router.message(StateFilter(ReferralState.get_price), IsAdmin())
async def get_ref_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
    except ValueError:
        return await message.answer(
            text=templates.texts.error_message,
            reply_markup=kb.inline.cancel_kb()
        )

    await state.update_data(price=price)
    await state.set_state(ReferralState.get_admin)
    await message.answer(
        text=templates.texts.admin_create_ref_get_admin,
        reply_markup=kb.inline.cancel_kb()
    )


@admin_referral_router.message(StateFilter(ReferralState.get_admin), IsAdmin())
async def get_ref_admin(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ref = data['ref']
    price = data['price']
    admin_url = message.text

    async with db.get_session() as session:
        referral_repo = ReferralRepository(session=session)
        await referral_repo.create_referral(
            ref=ref,
            price=price,
            admin_url=admin_url
        )

    await state.clear()
    await message.answer(
        text=templates.texts.admin_create_ref_link_successful.format(
            admin=admin_url,
            price=data['price'],
            url=f"https://t.me/{(await message.bot.get_me()).username}?start={data['ref']}"
        ),
    )


@admin_referral_router.callback_query(F.data.startswith('referrals_swipe:'), IsAdmin())
async def referrals_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    raw = int(call.data.split(':')[1])

    async with db.get_session() as session:
        user_repo = UserRepository(session)
        referrals = await user_repo.get_unique_refs()

        raw = int(call.data.split(':')[-1])
        await call.message.edit_reply_markup(
            reply_markup=kb.inline.admin_referrals(
                referrals=referrals,
                raw=raw
            )
        )
