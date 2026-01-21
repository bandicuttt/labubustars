import asyncio
from contextlib import suppress
from typing import List, Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from app.database import db
from app.database.repositories import UserRepository
from app.keyboards import inline
from app.templates import texts
from app.utils.advert_service import adverts_client
from app.utils.gift_miner import LOTTERY_CB_PREFIX, LotterySG, ensure_game_initialized, KEY_GRID, KEY_ATTEMPTS, \
    KEY_LOTTERY_MSG_ID, KEY_BONUS_USED, build_grid_kb, GRID_SIZE, lottery_caption, CB_MORE, KEY_SPONSORS_MSG_ID, \
    on_more_process
from app.templates.texts import gift_miner_lose_first, gift_miner_lose_final
from op.services.op_service import OPService

miner_router = Router(name="lottery")

op_service = OPService()


# Нажатие по ячейке
# @miner_router.callback_query(F.data.startswith(f"{LOTTERY_CB_PREFIX}:tap:"))
async def on_tap(cb: CallbackQuery, state: FSMContext):
    await state.set_state(LotterySG.active)
    await ensure_game_initialized(state)
    data = await state.get_data()

    grid: List[int] = data[KEY_GRID]
    attempts: int = data[KEY_ATTEMPTS]
    lottery_msg_id: Optional[int] = data.get(KEY_LOTTERY_MSG_ID)
    bonus_used: bool = data.get(KEY_BONUS_USED, False)

    # Если нет шансов — показываем lose-клавиатуру
    if attempts <= 0:
        kb = build_grid_kb(
            grid,
            show_more_menu=True,
            allow_more=not bonus_used  # <— только один раз
        )
        text = gift_miner_lose_first if not bonus_used else gift_miner_lose_final
        if lottery_msg_id:
            await cb.message.edit_text(text, reply_markup=kb)
        else:
            await cb.message.answer(text, reply_markup=kb)
        await cb.answer()
        return

    # --- ниже как было ---
    try:
        _, _, idx_str = cb.data.split(":")
        idx = int(idx_str)
    except Exception:
        await cb.answer("Ошибка нажатия", show_alert=False)
        return

    if not (0 <= idx < GRID_SIZE * GRID_SIZE):
        await cb.answer("Некорректная клетка", show_alert=False)
        return

    if grid[idx] == 1:
        await cb.answer()
        return

    grid[idx] = 1
    attempts -= 1
    await state.update_data({KEY_GRID: grid, KEY_ATTEMPTS: attempts})

    if attempts > 0:
        kb = build_grid_kb(grid, show_more_menu=False)
        caption = lottery_caption(attempts)
    else:
        # закончились — покажем lose и учтём бонус
        kb = build_grid_kb(
            grid, show_more_menu=True, allow_more=not bonus_used
        )
        caption = gift_miner_lose_first if not bonus_used else gift_miner_lose_final
        if not bonus_used:
            asyncio.create_task(adverts_client.start_advert_spam(cb.from_user.id))

    try:
        if lottery_msg_id and cb.message.message_id == lottery_msg_id:
            await cb.message.edit_text(caption, reply_markup=kb)
        else:
            await cb.message.edit_text(caption, reply_markup=kb)
            await state.update_data({KEY_LOTTERY_MSG_ID: cb.message.message_id})
    except Exception:
        with suppress(Exception):
            await cb.message.delete()
        sent = await cb.message.answer(caption, reply_markup=kb)
        await state.update_data({KEY_LOTTERY_MSG_ID: sent.message_id})

    await cb.answer()


@miner_router.callback_query(F.data == CB_MORE)
async def on_more(cb: CallbackQuery, state: FSMContext):
    return await on_more_process(cb, state)
