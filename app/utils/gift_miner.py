import random
from contextlib import suppress
from typing import List

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database import db
from app.database.repositories import UserRepository
from app.keyboards import inline
from app.templates import texts
from op.services import op_service

# ==========================
# Константы/настройки
# ==========================
GRID_SIZE = 5  # поле GRID_SIZE x GRID_SIZE
START_ATTEMPTS = 3  # стартовые попытки
LOTTERY_CB_PREFIX = "darts"  # префикс для callback_data

# Ключи в FSM-состоянии
KEY_GRID = "grid"
KEY_ATTEMPTS = "attempts"
KEY_LOTTERY_MSG_ID = "lottery_msg_id"
KEY_SPONSORS_MSG_ID = "sponsors_msg_id"
KEY_BONUS_USED = "bonus_used"

# Кнопки меню (минимум — “в меню”, ты можешь повесить на неё свой роутер)
BTN_MENU_TEXT = "В меню"
BTN_MENU_CB = "main_menu"


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
    highlight_idx = None
    if not allow_more:
        candidates = [i for i, v in enumerate(grid) if v == 0]
        if candidates:
            highlight_idx = random.choice(candidates)

    for r in range(GRID_SIZE):
        row_buttons = []
        for c in range(GRID_SIZE):
            idx = r * GRID_SIZE + c
            if grid[idx] == 1:
                text = "❌"
            else:
                # в одном случайном пустом поле ставим галочку
                text = "✅" if highlight_idx is not None and idx == highlight_idx else "🔘"
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


async def show_lottery(message: Message, state: FSMContext):
    await state.set_state(LotterySG.active)
    await ensure_game_initialized(state)

    data = await state.get_data()
    grid: List[int] = data[KEY_GRID]
    attempts: int = data[KEY_ATTEMPTS]

    kb = build_grid_kb(grid, show_more_menu=False)
    sent = await message.answer(lottery_caption(attempts), reply_markup=kb)

    await state.update_data({KEY_LOTTERY_MSG_ID: sent.message_id, KEY_SPONSORS_MSG_ID: None})


async def on_more_process(cb: CallbackQuery, state: FSMContext):
    await state.set_state(LotterySG.active)
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
    sponsors_kb = await op_service.op_client.check(
        user_id=cb.from_user.id,
        language_code=language_code,
        message=cb.message,
        no_manual=False,
        no_subgram=True,
        no_flyer=True,
        done_cb=CB_MORE,
    )

    if sponsors_kb:
        sent = await cb.message.answer(texts.after_dart_sub, reply_markup=sponsors_kb)
        with suppress(Exception):
            await cb.message.delete()
        await state.update_data({KEY_SPONSORS_MSG_ID: sent.message_id})
        await cb.answer()
        return

    # Подписок уже нет → выдаём +3 и помечаем бонус как использованный
    async with db.get_session() as session:
        user_repo = UserRepository(session)
        await user_repo.set_user_subbed(cb.from_user.id, subbed=True, second=True)
    data = await state.get_data()
    # grid: List[int] = data[KEY_GRID]
    # attempts: int = data[KEY_ATTEMPTS] + 3
    #
    # await state.update_data({
    #     KEY_ATTEMPTS: attempts,
    #     KEY_BONUS_USED: True,     # <— важно!
    #     KEY_SPONSORS_MSG_ID: None
    # })

    await cb.message.answer_dice('🎯')
    with suppress(Exception):
        await cb.message.delete()
    await cb.message.answer(text=texts.after_dart_sub_second, reply_markup=inline.cancel_kb())

    await cb.answer()

