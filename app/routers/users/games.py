import asyncio
import config
import time
import random
import json

from datetime import timedelta
from contextlib import suppress

from loader import bot

from aiogram import Router, types, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.utils.scheduler_instance import scheduler
from app.routers.start import send_main_menu
from app.utils.misc_function import get_time_now, get_remaining_time
from app.database.repositories.user_repo import UserRepository
from app.templates import texts
from app import keyboards as kb
from app.filters import IsPrivate
from app.database.models.user import User
from app.database import db, redis_pool
from app.states.games import GameState
from app.utils.utils import check_win
from app.utils.captcha_logic import *


games_router = Router(name='games_router')

active_captchas = {}

@games_router.callback_query(F.data.startswith('captcha:'))
async def handle_captcha(call: types.CallbackQuery, user: User):
    user_id = user.user_id
    captcha_key = f'captcha:{user_id}'
    message_id = call.message.message_id
    token = call.data.split(':')[1]

    if not await verify_captcha(user_id, message_id, token):
        await call.answer("❌ Неверно! Пробуем снова...")
        await delete_old_captcha(user_id, message_id)
        await send_new_captcha(user_id)
        return

    storage.remove(user_id)

    async with redis_pool.get_connection() as redis:
        await redis.set(captcha_key, 0)

    async with db.get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.update_user(
            user_id=user.user_id,
            important_action=True,
            balance=user.balance + config.CLICKER_GAME_REWARD,
        )
    await call.answer(
        f'✅ Ты получил {config.CLICKER_GAME_REWARD} ⭐️',
        show_alert=True
    )
    await delete_old_captcha(user_id, message_id)
    return await send_main_menu(call.message)

@games_router.callback_query(F.data == 'clicker')
async def clicker_game(call: types.CallbackQuery, state: FSMContext, user: User):

    key = f'clicker:{call.from_user.id}'
    captcha_key = f'captcha:{call.from_user.id}'

    async with redis_pool.get_connection() as redis:
        
        exists = await redis.get(key)
        captcha_status = await redis.get(captcha_key)

        # Не пройдена капча
        if captcha_status and bool(int(captcha_status)):
            await call.message.delete()
            return await send_new_captcha(user.user_id)

        if not exists:

            # 15% шанс на капчу
            if random.random() <= 0.15:
                await call.message.delete()
                await redis.set(captcha_key, 1)
                return await send_new_captcha(user.user_id)

            # Если таймера нет - начисляем награду
            await redis.set(key, int(time.time()), ex=config.CLICKER_GAME_RELOAD_TIME)
            
            async with db.get_session() as session:
                user_repo = UserRepository(session)
                user = await user_repo.update_user(
                    user_id=user.user_id,
                    important_action=True,
                    balance=user.balance + config.CLICKER_GAME_REWARD,
                )
                await call.answer(
                    f'✅ Ты получил {config.CLICKER_GAME_REWARD} ⭐️',
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

        # Умное форматирование времени
        if minutes > 0:
            time_str = f"{minutes} мин {seconds:02d} сек"
        else:
            time_str = f"{seconds} сек"

        await call.answer(
            f'⏳ Подожди {time_str} перед следующим кликом',
            show_alert=True
        )
        

@games_router.callback_query(F.data=='roulette', IsPrivate())
async def games_main_menu(call: types.CallbackQuery, state: FSMContext, user: User):
    await state.clear()

    with suppress(TelegramBadRequest, TelegramForbiddenError):
        await call.message.edit_media(
            media=types.InputMediaPhoto(
                media=config.GAMES_MENU_ID,
            )
        )
        await call.message.edit_caption(
            caption=texts.user_games_main_message,
            reply_markup=kb.inline.games_main_menu()
        )
        return

    return await send_main_menu(call.message)

@games_router.callback_query(F.data=='games_main_menu')
async def games_main_menu(call: types.CallbackQuery, state: FSMContext, user: User):
    await state.clear()

    await call.message.edit_media(
        media=types.InputMediaPhoto(
            media=config.GAMES_MENU_ID,
        )
    )

    await call.message.edit_caption(
        caption=texts.user_games_main_message,
        reply_markup=kb.inline.games_main_menu()
    )

@games_router.callback_query(F.data.startswith('game:'))
async def games_func(call: types.CallbackQuery, state: FSMContext, user: User):
    await state.clear()

    async with redis_pool.get_connection() as con:

        jackpot = await con.get('jackpot')

        if not jackpot:
            jackpot = 0
            await con.set('jackpot', value=0)
        else:
            jackpot = float(jackpot)

    selected_game = call.data.split(':')[1]
    action = call.data.split(':')[2]

    # Меню игры (описание)
    if action == 'games_menu':

        text = {
            'football': texts.football_main_message,
            'darts': texts.darts_main_message,
            'bowling': texts.bowling_main_message,
            'slots': texts.slots_main_message,
            'basketball': texts.basketball_main_message,
        }

        return await call.message.edit_caption(
            caption=text[selected_game].format(
                jackpot=round(jackpot, 2)
            ),
            reply_markup=kb.inline.selected_game_menu(selected_game)
        )

    # Правила
    if action == 'rules':
        text = {
            'football': texts.football_rules_message,
            'darts': texts.darts_rules_message,
            'bowling': texts.bowling_rules_message,
            'slots': texts.slots_rules_message,
            'basketball': texts.basketball_rules_message,
        }
        return await call.message.edit_caption(
            caption=text[selected_game].format(
                jackpot=jackpot
            ),
            reply_markup=kb.inline.back_kb(calldata=f'game:{selected_game}:games_menu')
        )

    if action == 'bet_menu':
        bet = 1.0
        if user.balance < 1:
            return await call.message.edit_caption(
                caption=texts.not_enough_money,
                reply_markup=kb.inline.not_enough_money(game=selected_game)
            )

        await state.set_state(GameState.get_bet)
        await state.set_data({
            'game': selected_game,
            'bet': bet,
            'message_id': call.message.message_id,
        })
        await call.message.edit_caption(
            caption=texts.set_bet_message.format(
                balance=round(user.balance, 2)
            ),
            reply_markup=kb.inline.game_bet_menu(game=selected_game, bet=bet)
        )

@games_router.callback_query(
    F.data.startswith('pre_start:'),
    StateFilter(GameState.get_bet),
    IsPrivate()
)
async def edit_bet_func(call: types.CallbackQuery, state: FSMContext, user: User):
    state_data = await state.get_data()

    game = call.data.split(':')[1]
    bet = state_data['bet']

    if game != state_data['game']:
        await state.clear()
        return await call.message.delete()

    action = call.data.split(':')[2]

    if action == 'lower_bet':

        if bet <= 1:
            return await call.answer(text=texts.bet_min_error, show_alert=True)

        bet-=1

    if action == 'highter_bet':

        if bet + 1 > user.balance:
            return await call.answer(text=texts.bet_max_error, show_alert=True)

        bet+=1

    if action in ['min_bet', 'delete_bet']:
        bet = 1

    if action == 'max_bet':
        bet = user.balance

    await state.update_data(bet=bet)

    with suppress(TelegramBadRequest):
        return await call.message.edit_caption(
                caption=texts.set_bet_message.format(
                    balance=round(user.balance, 2)
                ),
                reply_markup=kb.inline.game_bet_menu(game=game, bet=bet)
            )
    return await send_main_menu(call.message)


@games_router.message(
    IsPrivate(),
    StateFilter(GameState.get_bet)
)
async def edit_bet_message_func(message: types.Message, state: FSMContext, user: User):
    state_data = await state.get_data()
    await message.delete()

    with suppress(ValueError):
        new_bet = float(message.text)

    game = state_data['game']

    if new_bet < 1:
        return await message.answer(
            text=texts.bet_min_error,
            reply_markup=kb.inline.back_kb(calldata=f'game:{game}:games_menu')
        )

    if new_bet > user.balance:
        return await message.answer(
            text=texts.bet_max_error,
            reply_markup=kb.inline.not_enough_money(game=game)
        )

    await state.update_data(bet=new_bet)

    with suppress(TelegramBadRequest):
        return await message.bot.edit_message_caption(
            chat_id=message.from_user.id,
            message_id=state_data['message_id'],
            caption=texts.set_bet_message.format(
                balance=round(user.balance, 2)
            ),
            reply_markup=kb.inline.game_bet_menu(game=game, bet=new_bet)
        )
    return await send_main_menu(message)

def check_jackpot_win(bet: int, jackpot: int) -> bool:
    """
    Проверяет, выиграл ли пользователь джекпот
    
    Условия выигрыша:
    1. Джекпот > 300
    2. Ставка > 100
    3. (Джекпот - ставка*2) >= 100 (запас)
    4. Случайное срабатывание (3% шанс)
    """
    if (
            jackpot > 300
            and bet > 100
            and  (jackpot - bet * 2) >= 100
            and random.random() <= 0.03
        ):
        return True
    return False

@games_router.callback_query(
    IsPrivate(),
    F.data.startswith('start_game'),
    StateFilter(GameState.get_bet)
)
async def start_game_func(call: types.CallbackQuery, state: FSMContext, user: User):
    async with redis_pool.get_connection() as con:
        jackpot = float(await con.get('jackpot'))

    state_data = await state.get_data()

    await state.clear()

    bet = state_data['bet']
    game = state_data['game']
    win_amount = 0

    game_name = {
        'darts': '🎯',
        'slots': '🎰',
        'football': '⚽️',
        'bowling': '🎳',
        'basketball': '🏀',
    }

    game_symbol = {
        'darts': call.message.answer_dice('🎯'),
        'slots': call.message.answer_dice('🎰'),
        'football': call.message.answer_dice('⚽️'),
        'bowling': call.message.answer_dice('🎳'),
        'basketball': call.message.answer_dice('🏀'),
    }

    if bet < 1 or bet > user.balance:
        return await call.message.delete()

    value = (await game_symbol[game]).dice.value
    await asyncio.sleep(4)
    multiplier = check_win(game=game, value=value)
    print(multiplier)
    if not isinstance(multiplier, bool):
        win_amount = bet * multiplier
    
    # Если проиграл всё
    if not multiplier:
        jackpot+=float(bet / 2)
        await call.message.answer(text=texts.game_lose_message)

    # Ставка сохранилась
    elif multiplier == 1:
        await call.message.answer(text=texts.game_last_chance_message)

    # Сгорела не вся ставка
    elif multiplier < 1:
        jackpot+=float((bet-win_amount) / 2)
        await call.message.answer(text=texts.game_lower_then_bet_message.format(multiplier=multiplier, win_amount=win_amount))

    # Выигрыш
    elif multiplier > 1:
        if check_jackpot_win(bet, jackpot):
            print('jackpot')
            async with redis_pool.get_connection() as con:
                await con.set('jackpot', value=0)

            win_amount = jackpot  

            await call.message.answer(texts.jackpot_win_message.format(win_amount))
            await bot.send_photo(
                photo=config.GAMES_MENU_ID,
                chat_id=config.MAIN_CHAT_ID,
                caption=texts.jackpot_win_chat_message.format(
                    user.user_id,
                    game_name[game],
                    win_amount
                ),
                reply_markup=kb.inline.open_casino_kb(
                        config.BOT_USERNAME
                    )
            )
        else:
            await call.message.answer(
                text=texts.game_win_message.format(
                    multiplier=multiplier,
                    win_amount=win_amount
                ),
                
            )
            if bet > (user.balance / 2): 

                await bot.send_message(
                    chat_id=config.MAIN_CHAT_ID,
                    text=texts.risk_message.format(
                        user.user_id,
                        game_name[game],
                        win_amount
                    ),
                    reply_markup=kb.inline.open_casino_kb(
                        config.BOT_USERNAME
                    )
                )


    async with db.get_session() as session:
        user_repo = UserRepository(session)
        await user_repo.update_user(
            user_id=user.user_id,
            important_action=True,
            balance=user.balance+(win_amount-bet)
        )

    new_user_balance = user.balance+(win_amount-bet)

    if new_user_balance < 1:

        await call.message.edit_caption(
            caption=texts.not_enough_money,
            reply_markup=kb.inline.not_enough_money(game=game)
        )
        await state.clear()
        return await send_main_menu(call.message)

    if new_user_balance < bet:
        bet = 1

    await state.set_state(GameState.get_bet)
    await state.set_data({
        'game': game,
        'bet': bet,
        'message_id': call.message.message_id,
    })
    await call.message.answer_photo(
        photo=config.GAMES_MENU_ID,
        caption=texts.set_bet_message.format(
            balance=round(user.balance, 2)
        ),
        reply_markup=kb.inline.game_bet_menu(game=game, bet=bet)
    )

    async with redis_pool.get_connection() as con:
        await con.set('jackpot', value=jackpot)


async def add_to_jackpot(ticket_price: int):
    bonus_percent = random.uniform(0.3, 0.5)
    bonus = int(ticket_price * bonus_percent)
    
    async with redis_pool.get_connection() as redis:
        await redis.incrby('lottery:jackpot', bonus)

    return True

async def get_jackpot():

    async with redis_pool.get_connection() as redis:
        lottery_jackpot = int(await redis.get('lottery:jackpot') or 0)

        return lottery_jackpot if lottery_jackpot >= 100 else 100
