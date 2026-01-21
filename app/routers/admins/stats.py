from app.filters import IsAdmin, IsPrivate
from app import templates, keyboards as kb
from app.utils.utils import get_times, get_stat
from app.utils.stats import audit_stat

from aiogram import types, Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

admin_stats_router = Router(name='admin_stats_router')


@admin_stats_router.message(F.text == templates.button_texts.admin_stats_button, IsAdmin(), StateFilter('*'))
async def start_menu(message: types.Message, state: FSMContext):
    await state.clear()

    today, week_ago, month_ago, year_ago = get_times()
    await message.answer_photo(
        photo=types.FSInputFile(path=await audit_stat(today))
    )
    await message.answer(
        text=templates.texts.admin_stats_message.format(
            date_frame=today.strftime('%d.%m.%Y'),
            **await get_stat(today)
        ),
        reply_markup=kb.inline.admin_stats_kb()
    )


@admin_stats_router.callback_query(F.data.startswith('admin_stat:'), IsPrivate(), StateFilter('*'))
async def admin_stat_dateframe(call: types.CallbackQuery, state: FSMContext):
    await state.clear()

    today, week_ago, month_ago, year_ago = get_times()
    dateframe = call.data.split(':')[-1]

    if dateframe == 'today':
        dateframe = today
    elif dateframe == 'week':
        dateframe = week_ago
    else:
        dateframe = month_ago

    # await call.message.answer_photo(
    #     photo=types.FSInputFile(path=await ref_stat(today))
    # )
    await call.message.answer_photo(
        photo=types.FSInputFile(path=await audit_stat(today))
    )
    await call.message.answer(
        text=templates.texts.admin_stats_message.format(
            date_frame=dateframe.strftime('%d.%m.%Y'),
            **await get_stat(dateframe)
        ),
        reply_markup=kb.inline.admin_stats_kb()
    )
