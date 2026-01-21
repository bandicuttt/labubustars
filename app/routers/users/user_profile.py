import time
from app.database.models.promocodes import Promocode
import config

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from app.utils.misc_function import get_time_now
from app.keyboards.inline import profile_user, back_kb, approve_kb
from app.templates.texts import get_profile_message, send_transfer_message, send_transfer_check_message
from app.filters import IsPrivate, ReferralFilter
from app.database.models.user import User
from app.database import db, redis_pool
from app.database.repositories import UserRepository, PromocodeRepository, ActionHistoryRepository
from app.routers.start import send_main_menu

from loader import bot
from config import MEDIA_DIR

import random
from datetime import timedelta


user_profile_router = Router(name='user_profile_router')

@user_profile_router.callback_query(F.data=='profile', IsPrivate())
async def get_stars(call: types.CallbackQuery, state: FSMContext, user: User):
    
    async with db.get_session() as session:
        user_repo = UserRepository(session)
        total_refed = await user_repo.get_users(ref = str(call.from_user.id), count=True)
        total_subbed = await user_repo.get_users(ref = str(call.from_user.id), subbed=True, count=True)
        inactive_users, repeat_count = await user_repo.get_inactive_users(referrer_user_id=str(user.user_id))

    await call.message.delete()
    await call.message.answer_photo(
        photo=config.PROFILE_MAIN_MENU_ID,
        caption=get_profile_message.format(
            call.from_user.full_name,
            call.from_user.id,
            total_refed,
            total_subbed,
            repeat_count, 
            round(user.balance, 2),
        ),
        reply_markup=profile_user()
    )

@user_profile_router.callback_query(F.data=='promocode', IsPrivate())
async def promocode(call: types.CallbackQuery, state: FSMContext, user: User):
    await state.clear()

    await call.message.edit_caption(
        reply_markup=back_kb(
            calldata='main_menu',
            text='⬅️ В главное меню'
        ),
        caption=f'''
<i>✨ Для получения звезд на твой баланс введи промокод:
Найти промокоды можно в <a href="{config.MAIN_CHANNEL_URL}">канале</a> и <a href="{config.MAIN_CHAT_URL}">чате</a></i>
'''
    )
    await state.set_state('get_promocode')



@user_profile_router.message(StateFilter('get_promocode'), IsPrivate())
async def get_promocode(message: types.Message, state: FSMContext, user: User):
    
    promocode_code = message.text
    user_id = message.from_user.id
    key = f'promocode:{user_id}:{promocode_code}'

    async with redis_pool.get_connection() as redis:

        if await redis.get(key):
            await message.answer('❌ Промокод не действителен')
            return await send_main_menu(message)

        async with db.get_session() as session:
            promocode_repo = PromocodeRepository(session)
            promocode: Promocode | None = await promocode_repo.get_promocode_by_code(code=promocode_code)
            
            if not promocode or promocode.activations <= promocode.activated:
                await message.answer('❌ Промокод не действителен')
                return await send_main_menu(message)
            
            await redis.set(key, 'exists')
            
            user_repo = UserRepository(session)
            
            await user_repo.update_user(
                user_id=user.user_id,
                important_action=True,
                balance=user.balance + promocode.amount
            )
            await promocode_repo.update_promocode(
                promocode_id=promocode.id,
                activated=promocode.activated + 1
            )
            
            await message.answer(f'✅ Ты получил {promocode.amount} ⭐️', show_alert=True)
            return await send_main_menu(message)


@user_profile_router.callback_query(F.data=='transfer_stars', IsPrivate())
async def transfer_stars_menu(call: types.CallbackQuery, state: FSMContext, user: User):
    await call.message.edit_media(
        media=types.InputMediaPhoto(
            media=config.DEPOSIT_MENU_ID
        )
    )
    await call.message.edit_caption(
        caption=send_transfer_message,
        reply_markup=back_kb(
            calldata='main_menu',
            text='⬅️ В главное меню'
        ),
    )
    await state.set_state('get_uid_for_transfer')


@user_profile_router.message(StateFilter('get_uid_for_transfer'), ReferralFilter(), IsPrivate())
async def get_uid_for_transfer_func(message: types.Message, state: FSMContext, user: User):

    async with db.get_session() as session:
        user_repo = UserRepository(session)

        if not message.text.isdigit() or not await user_repo.get_user(user_id=int(message.text)):
            await state.clear()
            await message.answer('❌ Пользователь не найден!')
            return await send_main_menu(message)


    await message.answer('Введи сумму звёзд, которую ты хочешь отправить 👇')
    await state.set_state('get_stars_amount_for_transfer')
    await state.set_data({'uid': message.text})

@user_profile_router.message(StateFilter('get_stars_amount_for_transfer'), ReferralFilter(), IsPrivate())
async def get_uid_for_transfer_func(message: types.Message, state: FSMContext, user: User):
    
    if not message.text.isdigit() or float(message.text) > user.balance or float(message.text) <= 0:
        await state.clear()
        await message.answer('❌ У вас недостаточно ⭐️!')
        return await send_main_menu(message)

    uid = (await state.get_data())['uid']
    await state.update_data(amount=float(message.text))
    
    await message.answer(
        text=send_transfer_check_message.format(
            uid,
            float(message.text),
            round(user.balance - float(message.text), 2)
        ),
        reply_markup=approve_kb()
    )

@user_profile_router.callback_query(StateFilter('get_stars_amount_for_transfer'), ReferralFilter(), IsPrivate())
async def approve_transfer(call: types.CallbackQuery, state: FSMContext, user: User):
    data = await state.get_data()
    amount = float(data['amount'])
    uid = int(data['uid'])
    await state.clear()

    if float(amount) > user.balance or float(amount) <= 0:

        await call.message.answer('❌ У вас недостаточно ⭐️!')
        return await send_main_menu(call.message)

    async with db.get_session() as session:
        user_repo = UserRepository(session)
        action_history_repo = ActionHistoryRepository(session)
        receiver = await user_repo.get_user(user_id=uid)

        await user_repo.update_user(
            user_id=user.user_id,
            balance=user.balance - amount
        )
        await user_repo.update_user(
            user_id=receiver.user_id,
            balance=receiver.balance + amount
        )
        # Записываем перевод в историю
        await action_history_repo.write_transfer_record(
            sender_id=user.user_id,
            receiver_id=receiver.user_id,
            amount=amount,
            sender_ref=user.ref,
            receiver_ref=receiver.ref,
            chat_id=user.user_id,
        )
    try:
        await call.message.answer('✅ Успешно завершено')
        await bot.send_message(
            chat_id=receiver.user_id,
            text=f'Вам поступил перевод {amount}⭐️!'
        )
    except:
        pass
    finally:
        return await send_main_menu(call.message)

@user_profile_router.callback_query(F.data=='daily_bonus', IsPrivate())
async def daily_bonus_menu(call: types.CallbackQuery, state: FSMContext, user: User):
    await state.clear()

    try:
        user_info = await bot.get_chat(call.from_user.id)
        bot_username = config.BOT_USERNAME

        if f'https://t.me/{bot_username}' not in (user_info.bio or ''):

            return await call.answer(
                '❌ Сначала поставь свою личную ссылку в описание профиля или измени настройки конфиденциальности',
                show_alert=True
            )
    except:
        return await call.answer(
            '❌ Сначала поставь свою личную ссылку в описание профиля или измени настройки конфиденциальности',
            show_alert=True
        )

    key = f'daily_reward:{call.from_user.id}'

    async with redis_pool.get_connection() as redis:
        exists = await redis.get(key)

        if not exists:

            await redis.set(key, int(time.time()), ex=config.DAILY_GAME_REWARD_TIME)
            
            async with db.get_session() as session:
                user_repo = UserRepository(session)
                user = await user_repo.update_user(
                    user_id=user.user_id,
                    balance=user.balance + config.DAILY_GAME_REWARD
                )
                await call.answer(
                    f'✅ Ты получил {config.DAILY_GAME_REWARD} ⭐️',
                    show_alert=True
                )
            return

        current_time = int(time.time())
        cooldown_end = int(exists) + config.CLICKER_GAME_RELOAD_TIME
        remaining = cooldown_end - current_time

        if remaining <= 0:
            await redis.delete(key)
            await call.answer("Попробуй снова!", show_alert=True)
            return

        minutes = remaining // 60
        seconds = remaining % 60

        if minutes > 0:
            time_str = f"{minutes} мин {seconds:02d} сек"
        else:
            time_str = f"{seconds} сек"

        await call.answer(
            f'⏳ Подожди {time_str} перед следующим кликом',
            show_alert=True
        )
    



# @user_profile_router.message(F.text==users_get_profile_button, IsPrivate())
# async def get_stars(message: types.Message, state: FSMContext, user: User):
#     await state.clear()

#     ref = str(message.from_user.id)

    # async with db.get_session() as session:
    #     user_repo = UserRepository(session)
    #     total_refed = await user_repo.get_users(ref=ref, count=True)
#         total_refed_today = await user_repo.get_count_users_offsets(
#             count=True,
#             offset1=datetime.now(),
#             offset2=get_times()[0],
#             ref=ref
#         )

#     await message.answer_photo(
#         photo=types.FSInputFile('app/static/profile.jpg'),
#         caption=get_profile_message.format(
#             user_fullname=message.from_user.full_name,
#             total_refed=total_refed,
#             total_refed_today=total_refed_today,
#             balance=user.balance
#         )
#     )