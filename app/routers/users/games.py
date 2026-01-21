import asyncio
import config
import time
import random
import json
import hmac
import hashlib
import secrets

from datetime import timedelta
from contextlib import suppress
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from loader import bot

from aiogram import Router, types, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from app.utils.scheduler_instance import scheduler
from app.routers.start import send_main_menu
from app.utils.misc_function import get_time_now, get_remaining_time
from app.utils.botohub_reward import ensure_botohub_reward_message, get_botohub_reward_remaining
from app.database.repositories.user_repo import UserRepository
from app.templates import texts
from app import keyboards as kb
from app.filters import IsPrivate
from app.database.models.user import User
from app.database import db, redis_pool
from app.states.games import GameState
from app.utils.utils import check_win
from app.utils.captcha_logic import *

from op.services.op_service import op_client


games_router = Router(name='games_router')

active_captchas = {}


PLANE_SPONSORS_PER_ATTEMPT = 4
PLANE_AD_DAILY_LIMIT = 2
PLANE_STAGE_ORDER = ("manual", "flyer", "subgram", "tgrass", "botohub")
PLANE_DONE_CB = "check_plane"
PLANE_STAGE_KEY = "plane:stage:{user_id}:{day}"
PLANE_AD_COUNT_KEY = "plane:ad_count:{user_id}:{day}"
PLANE_PENDING_KEY = "plane:pending:{user_id}:{day}"
PLANE_PENDING_META_KEY = "plane:pending_meta:{user_id}:{day}"


def _plane_sig(*parts: str) -> str:
    msg = "|".join(parts).encode("utf-8")
    secret = str(config.PLANEAPP_SIGN_SECRET).encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _normalize_plane_base_url(url: str) -> str:
    u = urlparse(url)
    p = u.path
    if p.endswith("/plane/"):
        p = p[:-1]
    return urlunparse((u.scheme, u.netloc, p, u.params, u.query, u.fragment))


def _add_query_params(url: str, params: dict[str, str]) -> str:
    u = urlparse(url)
    q = dict(parse_qsl(u.query, keep_blank_values=True))
    q.update(params)
    new_query = urlencode(q)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))


def _plane_day_and_ttl() -> tuple[str, int]:
    now = get_time_now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ttl = int((tomorrow - now).total_seconds())
    if ttl <= 0:
        ttl = 60 * 60 * 24
    return now.strftime("%Y%m%d"), ttl


async def get_plane_ad_count(user_id: int) -> int:
    day, _ = _plane_day_and_ttl()
    async with redis_pool.get_connection() as redis:
        value = await redis.get(PLANE_AD_COUNT_KEY.format(user_id=user_id, day=day))
    if value is None:
        return 0
    return int(value)


async def get_plane_stage_index(user_id: int) -> int:
    day, _ = _plane_day_and_ttl()
    async with redis_pool.get_connection() as redis:
        value = await redis.get(PLANE_STAGE_KEY.format(user_id=user_id, day=day))
    if value is None:
        return 0
    return int(value)


async def set_plane_stage_index(user_id: int, index: int) -> None:
    day, ttl = _plane_day_and_ttl()
    async with redis_pool.get_connection() as redis:
        await redis.set(
            PLANE_STAGE_KEY.format(user_id=user_id, day=day),
            index,
            ex=ttl,
        )


async def get_plane_pending_attempt(user_id: int) -> tuple[bool, int | None]:
    day, _ = _plane_day_and_ttl()
    async with redis_pool.get_connection() as redis:
        pending = bool(await redis.get(PLANE_PENDING_KEY.format(user_id=user_id, day=day)))
        if not pending:
            return False, None
        stage_index_raw = await redis.hget(PLANE_PENDING_META_KEY.format(user_id=user_id, day=day), "stage_index")
    stage_index = int(stage_index_raw) if stage_index_raw is not None else None
    return True, stage_index


async def set_plane_pending_attempt(user_id: int, stage_index: int | None = None) -> None:
    day, ttl = _plane_day_and_ttl()
    async with redis_pool.get_connection() as redis:
        await redis.set(PLANE_PENDING_KEY.format(user_id=user_id, day=day), 1, ex=ttl)
        if stage_index is not None:
            await redis.hset(
                PLANE_PENDING_META_KEY.format(user_id=user_id, day=day),
                "stage_index",
                stage_index,
            )
            await redis.expire(PLANE_PENDING_META_KEY.format(user_id=user_id, day=day), ttl)


async def clear_plane_pending_attempt(user_id: int) -> None:
    day, _ = _plane_day_and_ttl()
    async with redis_pool.get_connection() as redis:
        await redis.delete(PLANE_PENDING_KEY.format(user_id=user_id, day=day))
        await redis.delete(PLANE_PENDING_META_KEY.format(user_id=user_id, day=day))


async def get_plane_stage_sponsors(
    stage: str,
    user_id: int,
    language_code: str,
    message: types.Message | types.CallbackQuery,
) -> types.InlineKeyboardMarkup | None:
    if stage == "manual":
        return await op_client.check(
            user_id=user_id,
            language_code=language_code,
            message=message,
            no_flyer=True,
            no_subgram=True,
            no_manual=False,
            done_cb=PLANE_DONE_CB,
        )
    if stage == "flyer":
        return await op_client.check(
            user_id=user_id,
            language_code=language_code,
            message=message,
            no_flyer=False,
            no_subgram=True,
            no_manual=True,
            done_cb=PLANE_DONE_CB,
            max_op=PLANE_SPONSORS_PER_ATTEMPT,
        )
    if stage == "subgram":
        return await op_client.check(
            user_id=user_id,
            language_code=language_code,
            message=message,
            no_flyer=True,
            no_subgram=False,
            no_manual=True,
            done_cb=PLANE_DONE_CB,
            max_op=PLANE_SPONSORS_PER_ATTEMPT,
        )
    if stage == "tgrass":
        return await op_client.check_tgrass(
            user_id=user_id,
            language_code=language_code,
            message=message,
            done_cb=PLANE_DONE_CB,
            max_op=PLANE_SPONSORS_PER_ATTEMPT,
        )
    if stage == "botohub":
        return await op_client.check_botohub(
            user_id=user_id,
            done_cb=PLANE_DONE_CB,
        )
    return None


def _build_plane_url(user_id: int, ad: bool = False) -> str:
    run = secrets.token_urlsafe(10)
    uid = str(user_id)
    exp = str(int(time.time()) + int(config.PLANEAPP_LINK_TTL_SECONDS))
    seed = str(random.randint(1, 2_000_000_000))
    reward = f"{0.10 + (random.Random(int(seed)).random() * 0.90):.2f}"
    ad_flag = "1" if ad else "0"
    sig = _plane_sig(run, uid, exp, seed, reward, ad_flag)
    params: dict[str, str] = {
        "run": run,
        "uid": uid,
        "exp": exp,
        "seed": seed,
        "reward": reward,
        "sig": sig,
        "ad": ad_flag,
    }
    if ad and getattr(config, "ADSGRAM_BLOCK_ID", ""):
        params["abid"] = str(getattr(config, "ADSGRAM_BLOCK_ID"))
    return _add_query_params(
        _normalize_plane_base_url(config.PLANEAPP_URL),
        params,
    )


async def _send_plane(call: types.CallbackQuery, ad: bool = False) -> None:
    url = _build_plane_url(call.from_user.id, ad=ad)
    try:
        await call.message.edit_media(
            media=types.InputMediaPhoto(
                media=config.GAMES_MENU_ID,
            )
        )
        await call.message.edit_caption(
            caption=texts.plane_text,
            reply_markup=kb.inline.plane_kb(url),
        )
    except:
        m = await bot.send_photo(
            photo=config.GAMES_MENU_ID,
            chat_id=call.from_user.id,
            caption=texts.plane_text,
            reply_markup=kb.inline.plane_kb(url),
        )
    await asyncio.sleep(10)
    await send_main_menu(call.message)
    with suppress(TelegramBadRequest, TelegramForbiddenError, UnboundLocalError):
        await call.message.delete()
        await m.delete()

@games_router.callback_query(F.data=='plane')
async def plane_game(call: types.CallbackQuery, user: User):
    # await call.answer()
    pending, pending_stage_index = await get_plane_pending_attempt(call.from_user.id)
    if pending and pending_stage_index is not None:
        stage_index = pending_stage_index
    else:
        stage_index = await get_plane_stage_index(call.from_user.id)

    if stage_index >= len(PLANE_STAGE_ORDER):
        ad_count = await get_plane_ad_count(call.from_user.id)
        if ad_count >= PLANE_AD_DAILY_LIMIT:
            await call.answer("😔 Лимит попыток самолётика на сегодня исчерпан", show_alert=True)
            return await send_main_menu(call.message)
        return await _send_plane(call, ad=True)

    stage = PLANE_STAGE_ORDER[stage_index]
    reply_markup = await get_plane_stage_sponsors(
        stage=stage,
        user_id=call.from_user.id,
        language_code=(call.from_user.language_code or "ru"),
        message=call,
    )

    if reply_markup:
        await set_plane_pending_attempt(call.from_user.id, stage_index=stage_index)
        with suppress(TelegramForbiddenError, TelegramBadRequest):
            return await bot.send_photo(
                photo=config.MAIN_MENU_ID,
                chat_id=user.user_id,
                caption=texts.subscribes_message,
                reply_markup=reply_markup,
            )
        return None

    if stage == "botohub":
        await ensure_botohub_reward_message(call.from_user.id)

    await set_plane_stage_index(call.from_user.id, stage_index + 1)
    await clear_plane_pending_attempt(call.from_user.id)
    return await _send_plane(call, ad=False)


@games_router.callback_query(F.data == PLANE_DONE_CB, IsPrivate(), StateFilter("*"))
async def check_plane(call: types.CallbackQuery, state: FSMContext, user: User):
    pending, stage_index = await get_plane_pending_attempt(call.from_user.id)
    if not pending or stage_index is None:
        await call.answer()
        return await send_main_menu(call.message)

    if stage_index >= len(PLANE_STAGE_ORDER):
        await clear_plane_pending_attempt(call.from_user.id)
        await call.answer()
        return await send_main_menu(call.message)

    stage = PLANE_STAGE_ORDER[stage_index]
    reply_markup = await get_plane_stage_sponsors(
        stage=stage,
        user_id=call.from_user.id,
        language_code=(call.from_user.language_code or "ru"),
        message=call,
    )

    if reply_markup:
        with suppress(TelegramBadRequest, TelegramForbiddenError):
            await call.message.delete()
        await call.answer()
        return await call.message.answer(text=texts.subscribes_message, reply_markup=reply_markup)

    if stage == "botohub":
        await ensure_botohub_reward_message(call.from_user.id)

    with suppress(TelegramBadRequest, TelegramForbiddenError):
        await call.message.delete()

    await clear_plane_pending_attempt(call.from_user.id)
    await state.clear()

    if stage == "tgrass":
        await op_client.tgrass_reset_offers(call.from_user.id)

    await set_plane_stage_index(call.from_user.id, stage_index + 1)
    await call.answer()
    return await _send_plane(call, ad=False)


@games_router.message(F.text.startswith("🎁 Награда"), IsPrivate(), StateFilter("*"))
async def botohub_reward_status(message: types.Message):
    await ensure_botohub_reward_message(message.from_user.id)
    remaining = await get_botohub_reward_remaining(message.from_user.id)
    if remaining is None:
        return await message.answer("ℹ️ Сейчас нет активного таймера награды за подписки")
    return await message.answer(f"⏳ Награда за подписки придёт через {remaining}")

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
