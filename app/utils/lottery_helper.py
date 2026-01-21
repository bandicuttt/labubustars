from datetime import datetime, timedelta, timezone
from typing import List
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.utils.gift_miner import LotterySG, ensure_game_initialized, KEY_GRID, KEY_ATTEMPTS, lottery_caption, \
    build_grid_kb, KEY_LOTTERY_MSG_ID, KEY_SPONSORS_MSG_ID

LOTTERY_SEEN_KEY = "lottery:seen:{user_id}"
JUST_CREATED_WINDOW = timedelta(minutes=5)  # можно 2-10 минут


async def set_once_lottery_seen(redis_pool, user_id: int) -> bool:
    """
    Пытается атомарно установить флаг 'видел лотерею'.
    Возвращает True, если ключ успешно установлен (то есть это первый раз).
    Возвращает False, если ключ уже существовал (лотерея уже показывалась).
    """
    async with redis_pool.get_connection() as conn:
        # если хочешь TTL, используй: await conn.set(LOTTERY_SEEN_KEY.format(user_id=user_id), "1", exist="NX", ex=60*60*24*365*10)
        return await conn.set(LOTTERY_SEEN_KEY.format(user_id=user_id), "1", nx=True)


async def has_seen_lottery(redis_pool, user_id: int) -> bool:
    """
    Проверяет, показывалась ли уже лотерея пользователю.

    Возвращает:
        True  — если флаг 'видел лотерею' уже установлен,
        False — если ключа нет (лотерея ещё не показывалась).
    """
    async with redis_pool.get_connection() as conn:
        key = LOTTERY_SEEN_KEY.format(user_id=user_id)
        exists = await conn.exists(key)
        return bool(exists)


def is_just_created(user) -> bool:
    created_at: datetime | None = getattr(user, "created_at", None)
    if not created_at:
        return False
    now = datetime.now(timezone.utc if created_at.tzinfo else None)
    return (now - created_at) <= JUST_CREATED_WINDOW


async def show_lottery(message: Message, state: FSMContext):
    await state.set_state(LotterySG.active)
    await ensure_game_initialized(state)

    data = await state.get_data()
    grid: List[int] = data[KEY_GRID]
    attempts: int = data[KEY_ATTEMPTS]

    kb = build_grid_kb(grid, show_more_menu=False)
    sent = await message.answer(lottery_caption(attempts), reply_markup=kb)

    await state.update_data({KEY_LOTTERY_MSG_ID: sent.message_id, KEY_SPONSORS_MSG_ID: None})
