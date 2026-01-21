import json
import random
import time
from contextlib import suppress
from typing import Optional, Any
from urllib.parse import quote

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    FSInputFile,
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from app.database import db, redis_pool
from app.database.repositories import UserRepository
from app.database.repositories.bot_settings import SettingsRepository
from app.templates.texts import bad_catch, gift_miner_no_sponsors_message, gift_miner_referral_progress_message
from op.services.op_service import op_client, REDIS_CACHE_KEY

# ==========================
# Константы/настройки
# ==========================
GRID_SIZE = 3  # поле GRID_SIZE x GRID_SIZE
GRID_CLOSED = "💦"  # закрытая клетка
START_ATTEMPTS = 3  # стартовые попытки
SPONSORS_LIMIT = 8  # лимит спонсоров для показа
LOTTERY_CB_PREFIX = "fish"  # префикс для callback_data

START_CB = f"{LOTTERY_CB_PREFIX}:start"
VERIFY_CB = f"{LOTTERY_CB_PREFIX}:verify"
PLAY_AGAIN_CB = f"{LOTTERY_CB_PREFIX}:play_again"
GIFT_MINER_REF_CHECK_CB = f"{LOTTERY_CB_PREFIX}:check_referrals"

STATE_KEY = "fish_lottery_state:{user_id}"
GIFT_MINER_REF_BONUS_KEY = "fish:ref_bonus:{user_id}"

# Ключи состояния
KEY_STAGE = "stage"
KEY_ATTEMPTS = "attempts"
KEY_GRID = "grid"
KEY_LOTTERY_MSG_ID = "lottery_msg_id"
KEY_OP_MSG_ID = "op_msg_id"
KEY_WAITING_MSG_ID = "waiting_msg_id"
KEY_SPONSOR_ON_HIT = "sponsor_on_hit"
KEY_OP_MODE = "op_mode"
KEY_GIFT_MINER_SOURCES = "gift_miner_sources"
KEY_GIFT_MINER_CACHE_TS = "gift_miner_cache_ts"
KEY_PLAY_COUNT = "play_count"

STAGE_LOTTERY = "lottery"
STAGE_OP = "op"
STAGE_WAITING = "waiting"

OP_MODE_POST = "post"
OP_MODE_PRE = "pre"

SPONSOR_CACHE_TTL_SEC = 60 * 60

miner_router = Router(name="lottery")


# ==========================
# Вспомогательные функции
# ==========================
async def get_start_bonus_url() -> str | None:
    async with db.get_session() as session:
        settings_repo = SettingsRepository(session)
        start_bonus_url = await settings_repo.get("START_BONUS_URL")
    return start_bonus_url or getattr(config, "START_BONUS_URL", None)


def _empty_grid_text() -> str:
    return random.choice(bad_catch)


def _fish_grid_text() -> str:
    return random.choice(["🐟", "🐠", "🐡", "🦈", "🐬"])


def _normalize_grid(grid: list[Any]) -> tuple[list[Any], bool]:
    normalized = list(grid)
    changed = False
    for idx, value in enumerate(normalized):
        if value == 1:
            normalized[idx] = _empty_grid_text()
            changed = True
        elif value is None:
            normalized[idx] = 0
            changed = True
    return normalized, changed


def build_grid_kb(grid: list[Any]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in range(GRID_SIZE):
        row_buttons = []
        for c in range(GRID_SIZE):
            idx = r * GRID_SIZE + c
            text = GRID_CLOSED if grid[idx] == 0 else str(grid[idx])
            row_buttons.append(InlineKeyboardButton(text=text, callback_data=cb_tap(idx)))
        kb.row(*row_buttons)
    return kb.as_markup()


def lottery_caption(attempts_left: int, is_miss: bool) -> str:
    if is_miss:
        return f"🎣 Мимо! Осталось попыток: {attempts_left}."
    return f"🎣 Ловим рыбку! Осталось попыток: {attempts_left}."


def waiting_kb(start_bonus_url: str | None) -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text="🎣 Сыграть еще раз", callback_data=PLAY_AGAIN_CB)]]
    if start_bonus_url:
        keyboard.append([
            InlineKeyboardButton(text="🎁 Получить подарок", url=start_bonus_url),
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def cb_tap(idx: int) -> str:
    return f"{LOTTERY_CB_PREFIX}:tap:{idx}"


def _parse_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in {"1", "true", "yes"}


def _sponsor_required_for_play(play_count: int) -> bool:
    return play_count % 3 != 0


async def _next_play_meta(user_id: int, sponsor_on_hit: bool | None) -> tuple[int, bool]:
    data = await get_state(user_id)
    play_count = (data.get(KEY_PLAY_COUNT) or 0) + 1
    sponsor_on_hit = _sponsor_required_for_play(play_count) if sponsor_on_hit is None else sponsor_on_hit
    return play_count, sponsor_on_hit


async def _referral_invite_kb(message: Message, user_id: int) -> InlineKeyboardMarkup:
    bot_username = (await message.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    share_url = f"https://t.me/share/url?url={quote(ref_link)}"
    keyboard = [
        [InlineKeyboardButton(text="📨 Пригласить 3 друзей", url=share_url)],
        [InlineKeyboardButton(text="✅ Проверить друзей", callback_data=GIFT_MINER_REF_CHECK_CB)],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def get_state(user_id: int) -> dict[str, Any]:
    async with redis_pool.get_connection() as redis:
        data = await redis.hgetall(STATE_KEY.format(user_id=user_id))

    if not data:
        return {}

    result: dict[str, Any] = {}
    for key, value in data.items():
        key_str = key.decode() if isinstance(key, (bytes, bytearray)) else str(key)
        val_str = value.decode() if isinstance(value, (bytes, bytearray)) else value
        result[key_str] = val_str

    grid_raw = result.get(KEY_GRID)
    if grid_raw:
        result[KEY_GRID] = json.loads(grid_raw)
    result[KEY_ATTEMPTS] = _parse_int(result.get(KEY_ATTEMPTS))
    result[KEY_LOTTERY_MSG_ID] = _parse_int(result.get(KEY_LOTTERY_MSG_ID))
    result[KEY_OP_MSG_ID] = _parse_int(result.get(KEY_OP_MSG_ID))
    result[KEY_WAITING_MSG_ID] = _parse_int(result.get(KEY_WAITING_MSG_ID))
    result[KEY_SPONSOR_ON_HIT] = _parse_bool(result.get(KEY_SPONSOR_ON_HIT))
    result[KEY_PLAY_COUNT] = _parse_int(result.get(KEY_PLAY_COUNT))
    return result


async def update_state(user_id: int, **fields: Any) -> None:
    payload: dict[str, str] = {}
    for key, value in fields.items():
        if value is None:
            payload[key] = ""
        elif key == KEY_GRID:
            payload[key] = json.dumps(value)
        elif isinstance(value, bool):
            payload[key] = "1" if value else "0"
        else:
            payload[key] = str(value)

    if not payload:
        return

    async with redis_pool.get_connection() as redis:
        await redis.hset(STATE_KEY.format(user_id=user_id), mapping=payload)


async def clear_state(user_id: int) -> None:
    async with redis_pool.get_connection() as redis:
        await redis.delete(STATE_KEY.format(user_id=user_id))


async def delete_message_safe(message: Message, message_id: int | None) -> None:
    if not message_id:
        return
    with suppress(TelegramBadRequest, TelegramForbiddenError):
        await message.bot.delete_message(chat_id=message.chat.id, message_id=message_id)


async def fetch_sponsors_keyboard(
        user_id: int,
        language_code: str,
        context: Message | CallbackQuery,
        use_cache: bool = False,
) -> InlineKeyboardMarkup | None:
    cache_data = None
    source_limits: dict[str, int] | None = None
    if use_cache:
        async with redis_pool.get_connection() as redis:
            cache_raw = await redis.get(REDIS_CACHE_KEY.format(user_id))
            if cache_raw:
                if isinstance(cache_raw, (bytes, bytearray)):
                    cache_raw = cache_raw.decode()
                cache_data = json.loads(cache_raw)
                cached_at = _parse_int(cache_data.get(KEY_GIFT_MINER_CACHE_TS))
                if cached_at is None or time.time() - cached_at > SPONSOR_CACHE_TTL_SEC:
                    cache_data = None
                else:
                    source_limits = cache_data.get(KEY_GIFT_MINER_SOURCES)

    sponsors: list[Any] = []
    seen_urls: set[str] = set()
    remaining = SPONSORS_LIMIT

    source_counts: dict[str, int] = {
        "manual": 0,
        "subgram": 0,
        "tgrass": 0,
        "flyer": 0,
        "botohub": 0,
    }

    def append_unique(new_sponsors: list[Any], source: str) -> None:
        nonlocal remaining
        added = 0
        for sponsor in new_sponsors:
            if remaining <= 0:
                break
            if sponsor.url in seen_urls:
                continue
            sponsors.append(sponsor)
            seen_urls.add(sponsor.url)
            remaining -= 1

            added += 1
        source_counts[source] += added

    manual_limit = source_limits.get("manual") if source_limits else remaining
    if manual_limit > 0 and remaining > 0:
        manual_sponsors = await op_client.get_manual_sponsors(manual_limit, user_id, language_code, cache_data)
        append_unique(manual_sponsors, "manual")

    subgram_limit = source_limits.get("subgram") if source_limits else remaining
    if subgram_limit > 0 and remaining > 0:
        subgram_sponsors = await op_client.get_subgram_sponsors(subgram_limit, user_id, language_code, cache_data)
        append_unique(subgram_sponsors, "subgram")

    tgrass_limit = source_limits.get("tgrass") if source_limits else remaining
    if tgrass_limit > 0 and remaining > 0:
        tgrass_sponsors = await op_client.get_tgrass_sponsors(tgrass_limit, user_id, context, language_code)
        append_unique(tgrass_sponsors, "tgrass")

    flyer_limit = source_limits.get("flyer") if source_limits else remaining
    if flyer_limit > 0 and remaining > 0:
        flyer_sponsors = await op_client.get_flyer_sponsors(flyer_limit, user_id, language_code, cache_data)
        append_unique(flyer_sponsors, "flyer")

    botohub_limit = source_limits.get("botohub") if source_limits else remaining
    if botohub_limit > 0 and remaining > 0:
        botohub_sponsors = await op_client.get_botohub_sponsors(user_id)
        append_unique(botohub_sponsors, "botohub")

    if not use_cache or cache_data is None:
        await op_client.save_sponsors_cache(
            user_id,
            {
                KEY_GIFT_MINER_SOURCES: source_counts,
                KEY_GIFT_MINER_CACHE_TS: int(time.time()),
            },
        )
    if sponsors:
        return await op_client.build_reply_markup(sponsors[:SPONSORS_LIMIT], done_cb=VERIFY_CB)

    async with db.get_session() as session:
        print(f"USER {user_id} PASSED OP")
        user_repo = UserRepository(session)
        user = await user_repo.get_user(user_id)
        await user_repo.update_user(user_id, False, subbed=True, darts_op_count=user.darts_op_count + 1)

    return None


async def send_lottery(message: Message, user_id: int, sponsor_on_hit: bool | None) -> None:
    play_count, sponsor_on_hit = await _next_play_meta(user_id, sponsor_on_hit)
    grid = [0] * (GRID_SIZE * GRID_SIZE)
    attempts = START_ATTEMPTS
    kb = build_grid_kb(grid)
    sent = await message.answer_photo(
        photo=config.FISHING_PHOTO_ID,
        caption=lottery_caption(attempts, is_miss=False),
        reply_markup=kb,
    )

    await update_state(
        user_id,
        **{
            KEY_STAGE: STAGE_LOTTERY,
            KEY_GRID: grid,
            KEY_ATTEMPTS: attempts,
            KEY_SPONSOR_ON_HIT: sponsor_on_hit,
            KEY_LOTTERY_MSG_ID: sent.message_id,
            KEY_OP_MSG_ID: None,
            KEY_WAITING_MSG_ID: None,
            KEY_OP_MODE: "",
        },
    )


async def update_lottery_message(
    message: Message,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if message.photo:
        await message.edit_caption(caption=caption, reply_markup=reply_markup)
        return
    await message.edit_text(caption, reply_markup=reply_markup)


LOCAL_PHOTO_CACHE = {}


async def send_waiting(message: Message, user_id: int, lottery_msg_id: int | None = None) -> None:
    start_bonus_url = await get_start_bonus_url()
    photo_file = None
    photo_id = LOCAL_PHOTO_CACHE.get("fishing_waiting")
    if not photo_id:
        img_path = 'app/static/cheba_fishing.jpg'
        photo_file = FSInputFile(img_path)
    photo = photo_file if photo_id is None else photo_id
    sent = await message.answer_photo(
        photo=photo,
        caption="<b>Отличный улов, поздравляю🎣🎣🎣🎣🎣"
                "\n\n🎁 Ожидай получения подарка.</b>",
        reply_markup=waiting_kb(start_bonus_url),
    )
    await update_state(
        user_id,
        **{
            KEY_STAGE: STAGE_WAITING,
            KEY_WAITING_MSG_ID: sent.message_id,
            KEY_LOTTERY_MSG_ID: lottery_msg_id,
            KEY_OP_MSG_ID: None,
        },
    )


async def send_no_sponsors(message: Message, user_id: int) -> None:
    sent = await message.answer(
        gift_miner_no_sponsors_message,
        reply_markup=await _referral_invite_kb(message, user_id),
    )
    await update_state(
        user_id,
        **{
            KEY_STAGE: STAGE_WAITING,
            KEY_WAITING_MSG_ID: sent.message_id,
            KEY_OP_MSG_ID: None,
        },
    )


async def send_op_message(
        message: Message,
        context: Message | CallbackQuery,
        user_id: int,
        op_mode: str,
        use_cache: bool = False,
        lottery_msg_id: int | None = None,
) -> None:
    language_code = (context.from_user.language_code or "ru") if context.from_user else "ru"
    sponsors_kb = await fetch_sponsors_keyboard(user_id, language_code, context, use_cache=use_cache)

    if not sponsors_kb:
        if op_mode == OP_MODE_PRE:
            return await send_no_sponsors(message, user_id)
        return await send_waiting(message, user_id, lottery_msg_id=lottery_msg_id)

    if op_mode == OP_MODE_PRE:
        caption = "<b>Подпишись на спонсоров чтобы играть еще раз.</b>"
    else:
        caption = (
            "<b>Отличный улов, поздравляю🎣🎣🎣🎣🎣"
            "\n\nТы выиграл ПРИЗ🎁 подпишись на спонсоров ниже, чтобы забрать его👇👇👇</b>"
        )

    sent = await message.answer_photo(
        photo=config.SUBSCRIBE_PHOTO_ID,
        caption=caption,
        reply_markup=sponsors_kb,
    )

    await update_state(
        user_id,
        **{
            KEY_STAGE: STAGE_OP,
            KEY_OP_MODE: op_mode,
            KEY_OP_MSG_ID: sent.message_id,
            KEY_LOTTERY_MSG_ID: lottery_msg_id,
            KEY_WAITING_MSG_ID: None,
        },
    )


# ==========================
# Роутеры
# ==========================
@miner_router.callback_query(F.data == START_CB)
async def start_fishing(call: CallbackQuery, state: FSMContext):
    await state.clear()
    data = await get_state(call.from_user.id)

    await delete_message_safe(call.message, data.get(KEY_LOTTERY_MSG_ID))
    await delete_message_safe(call.message, data.get(KEY_OP_MSG_ID))
    await delete_message_safe(call.message, data.get(KEY_WAITING_MSG_ID))

    if data.get(KEY_STAGE) == STAGE_OP:
        op_mode = data.get(KEY_OP_MODE) or OP_MODE_POST
        await send_op_message(call.message, call, call.from_user.id, op_mode=op_mode, use_cache=True)
        await call.answer()
        return

    await clear_state(call.from_user.id)
    with suppress(TelegramBadRequest, TelegramForbiddenError):
        await call.message.delete()

    await send_lottery(call.message, call.from_user.id, sponsor_on_hit=None)
    await call.answer()


@miner_router.callback_query(F.data.startswith(f"{LOTTERY_CB_PREFIX}:tap:"))
async def on_tap(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    data = await get_state(cb.from_user.id)

    if data.get(KEY_STAGE) != STAGE_LOTTERY:
        await cb.answer()
        return

    grid: list[Any] = data.get(KEY_GRID) or [0] * (GRID_SIZE * GRID_SIZE)
    attempts: int = data.get(KEY_ATTEMPTS) or START_ATTEMPTS
    sponsor_on_hit: bool = data.get(KEY_SPONSOR_ON_HIT, True)

    grid, normalized = _normalize_grid(grid)
    if normalized:
        await update_state(cb.from_user.id, **{KEY_GRID: grid})

    try:
        _, _, idx_str = cb.data.split(":")
        idx = int(idx_str)
    except Exception:
        await cb.answer("Ошибка нажатия", show_alert=False)
        return

    if not (0 <= idx < GRID_SIZE * GRID_SIZE):
        await cb.answer("Некорректная клетка", show_alert=False)
        return

    if grid[idx] != 0:
        await cb.answer()
        return

    grid[idx] = 1
    attempts -= 1

    if attempts <= 0:
        grid[idx] = _fish_grid_text()
    else:
        grid[idx] = _empty_grid_text()

    if attempts > 0:
        await update_state(cb.from_user.id, **{KEY_GRID: grid, KEY_ATTEMPTS: attempts})
        kb = build_grid_kb(grid)
        await update_lottery_message(cb.message, lottery_caption(attempts, is_miss=True), kb)
        await cb.answer()
        return

    await update_state(cb.from_user.id, **{KEY_GRID: grid, KEY_ATTEMPTS: 0})
    with suppress(TelegramBadRequest, TelegramForbiddenError):
        kb = build_grid_kb(grid)
        await update_lottery_message(cb.message, lottery_caption(0, is_miss=False), kb)

    if sponsor_on_hit:
        await send_op_message(
            cb.message,
            cb,
            cb.from_user.id,
            op_mode=OP_MODE_POST,
            lottery_msg_id=cb.message.message_id,
        )
    else:
        await send_waiting(cb.message, cb.from_user.id, lottery_msg_id=cb.message.message_id)

    await cb.answer()


@miner_router.callback_query(F.data == VERIFY_CB)
async def verify_sponsors(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    data = await get_state(cb.from_user.id)

    if data.get(KEY_STAGE) != STAGE_OP:
        await cb.answer()
        return

    op_mode = data.get(KEY_OP_MODE) or OP_MODE_POST
    language_code = (cb.from_user.language_code or "ru") if cb.from_user else "ru"
    sponsors_kb = await fetch_sponsors_keyboard(cb.from_user.id, language_code, cb, use_cache=True)

    if sponsors_kb:
        await cb.message.answer(
            "Для получения подарка подпишись на спонсоров и нажми «Проверить».",
            reply_markup=sponsors_kb,
        )
        await cb.message.delete()
        await cb.answer()
        return

    if op_mode == OP_MODE_PRE:
        await send_lottery(cb.message, cb.from_user.id, sponsor_on_hit=None)
    else:
        await send_waiting(cb.message, cb.from_user.id)

    with suppress(TelegramBadRequest, TelegramForbiddenError):
        await cb.message.delete()

    await cb.answer()


@miner_router.callback_query(F.data == PLAY_AGAIN_CB)
async def play_again(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    data = await get_state(cb.from_user.id)

    await delete_message_safe(cb.message, data.get(KEY_WAITING_MSG_ID))
    await send_op_message(cb.message, cb, cb.from_user.id, op_mode=OP_MODE_PRE)
    await cb.answer()


@miner_router.callback_query(F.data == GIFT_MINER_REF_CHECK_CB)
async def check_referrals_for_gift_miner(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    async with db.get_session() as session:
        user_repo = UserRepository(session)
        total_subbed = await user_repo.get_users(
            ref=str(cb.from_user.id),
            subbed=True,
            count=True,
        )

    async with redis_pool.get_connection() as redis:
        used_raw = await redis.get(GIFT_MINER_REF_BONUS_KEY.format(user_id=cb.from_user.id))
        used = int(used_raw) if used_raw is not None else 0

    available = total_subbed // 3
    if available <= used:
        await cb.answer()
        await cb.message.answer(
            gift_miner_referral_progress_message.format(current=total_subbed),
            reply_markup=await _referral_invite_kb(cb.message, cb.from_user.id),
        )
        return

    async with redis_pool.get_connection() as redis:
        await redis.incr(GIFT_MINER_REF_BONUS_KEY.format(user_id=cb.from_user.id))

    with suppress(TelegramBadRequest, TelegramForbiddenError):
        await cb.message.delete()

    await send_lottery(cb.message, cb.from_user.id, sponsor_on_hit=False)
    await cb.answer()

