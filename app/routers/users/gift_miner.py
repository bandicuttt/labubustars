from contextlib import suppress
from dataclasses import dataclass
from typing import Optional, List

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.templates.texts import gift_miner_lose_first, gift_miner_lose_final
from op.services.op_service import OPService

# ==========================
# Константы/настройки
# ==========================
GRID_SIZE = 5  # поле GRID_SIZE x GRID_SIZE
START_ATTEMPTS = 3  # стартовые попытки
LOTTERY_CB_PREFIX = "lottery"  # префикс для callback_data

# Ключи в FSM-состоянии
KEY_GRID = "grid"
KEY_ATTEMPTS = "attempts"
KEY_LOTTERY_MSG_ID = "lottery_msg_id"
KEY_SPONSORS_MSG_ID = "sponsors_msg_id"
KEY_BONUS_USED = "bonus_used"

# Кнопки меню (минимум — “в меню”, ты можешь повесить на неё свой роутер)
BTN_MENU_TEXT = "В меню"
BTN_MENU_CB = "close"

op_service = OPService()


# Кнопки для лотереи
def cb_tap(idx: int) -> str:
    return f"{LOTTERY_CB_PREFIX}:tap:{idx}"


CB_MORE = f"{LOTTERY_CB_PREFIX}:more"  # +3 попытки
CB_VERIFY = f"{LOTTERY_CB_PREFIX}:verify"  # done_cb для спонсоров


# ==========================
# Типы и состояния
# ==========================
class LotterySG(StatesGroup):
    active = State()  # состояние активной игры


# ==========================
# Вспомогательные функции
# ==========================
def build_grid_kb(grid: List[int], show_more_menu: bool, allow_more: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for r in range(GRID_SIZE):
        row_buttons = []
        for c in range(GRID_SIZE):
            idx = r * GRID_SIZE + c
            text = "❌" if grid[idx] == 1 else "🔘"
            row_buttons.append(InlineKeyboardButton(text=text, callback_data=cb_tap(idx)))
        kb.row(*row_buttons)

    if show_more_menu:
        row = []
        if allow_more:
            row.append(InlineKeyboardButton(text="+3 попытки", callback_data=CB_MORE))
        row.append(InlineKeyboardButton(text=BTN_MENU_TEXT, callback_data=BTN_MENU_CB))
        kb.row(*row)

    return kb.as_markup()


def lottery_caption(attempts_left: int) -> str:
    return f"Лотерея 🎲\nУ тебя осталось {attempts_left} попыток."


async def ensure_game_initialized(state: FSMContext) -> None:
    data = await state.get_data()
    if KEY_GRID not in data or KEY_ATTEMPTS not in data:
        await state.update_data(
            **{
                KEY_GRID: [0] * (GRID_SIZE * GRID_SIZE),
                KEY_ATTEMPTS: START_ATTEMPTS,
                KEY_LOTTERY_MSG_ID: None,
                KEY_SPONSORS_MSG_ID: None,
                KEY_BONUS_USED: False,
            }
        )


# ==========================
# Публичный роутер
# ==========================
miner_router = Router(name="lottery")


async def show_lottery(message: Message, state: FSMContext):
    await state.set_state(LotterySG.active)
    await ensure_game_initialized(state)

    data = await state.get_data()
    grid: List[int] = data[KEY_GRID]
    attempts: int = data[KEY_ATTEMPTS]

    kb = build_grid_kb(grid, show_more_menu=False)
    sent = await message.answer(lottery_caption(attempts), reply_markup=kb)

    await state.update_data({KEY_LOTTERY_MSG_ID: sent.message_id, KEY_SPONSORS_MSG_ID: None})


# Нажатие по ячейке
@miner_router.callback_query(F.data.startswith(f"{LOTTERY_CB_PREFIX}:tap:"))
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
    await state.set_state(LotterySG.active)
    await ensure_game_initialized(state)
    data = await state.get_data()

    # если бонус уже использован — просто показать меню и выйти
    if data.get(KEY_BONUS_USED, False):
        with suppress(Exception):
            await cb.message.delete()
        kb = {'inline_keyboard': [{'text': '⬅️ В главное меню ', 'callback_data': 'main_menu'}]}
        await cb.message.answer("Бонус уже использован", reply_markup=kb)
        await cb.answer()
        return

    language_code = (cb.from_user.language_code or "ru") if cb.from_user else "ru"

    sponsors_kb = await op_service.check(
        user_id=cb.from_user.id,
        language_code=language_code,
        message=cb.message,
        no_flyer=True,
        no_subgram=True,
        no_manual=False,
        done_cb=CB_MORE,
    )

    if sponsors_kb:
        with suppress(Exception):
            await cb.message.delete()
        sent = await cb.message.answer("Подпишись на спонсоров, затем нажми «Проверить» 👇", reply_markup=sponsors_kb)
        await state.update_data({KEY_SPONSORS_MSG_ID: sent.message_id})
        await cb.answer()
        return

    # Подписок уже нет → выдаём +3 и помечаем бонус как использованный
    data = await state.get_data()
    grid: List[int] = data[KEY_GRID]
    attempts: int = data[KEY_ATTEMPTS] + 3

    await state.update_data({
        KEY_ATTEMPTS: attempts,
        KEY_BONUS_USED: True,     # <— важно!
        KEY_SPONSORS_MSG_ID: None
    })

    kb = build_grid_kb(grid, show_more_menu=False)
    with suppress(Exception):
        await cb.message.delete()
    sent = await cb.message.answer(lottery_caption(attempts), reply_markup=kb)
    await state.update_data({KEY_LOTTERY_MSG_ID: sent.message_id})

    await cb.answer()
