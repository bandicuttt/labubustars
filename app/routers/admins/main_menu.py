import json

from app import templates
from app import keyboards as kb
from app.database import db
from app.filters import IsAdmin

from app.database.repositories import PromocodeRepository, ActionHistoryRepository
from app.states.promocodes import PromocodeState

from aiogram import types, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


admin_menu_router = Router(name='admin_menu_router')


class AdminWaitFiles(StatesGroup):
    waiting_files = State()


def _extract_file_ids(message: types.Message) -> list[tuple[str, str]]:
    """
    Возвращает список (kind, file_id) из сообщения.
    kind — тип вложения для удобства.
    """
    found: list[tuple[str, str]] = []

    if message.document:
        found.append(("document", message.document.file_id))

    if message.photo:
        # photo — список sizes, берём самый большой
        found.append(("photo", message.photo[-1].file_id))

    if message.video:
        found.append(("video", message.video.file_id))

    if message.audio:
        found.append(("audio", message.audio.file_id))

    if message.voice:
        found.append(("voice", message.voice.file_id))

    if message.video_note:
        found.append(("video_note", message.video_note.file_id))

    if message.animation:
        found.append(("animation", message.animation.file_id))

    if message.sticker:
        found.append(("sticker", message.sticker.file_id))

    return found


@admin_menu_router.message(Command("admin_files"), IsAdmin())
async def admin_files_start(message: types.Message, state: FSMContext):
    await state.set_state(AdminWaitFiles.waiting_files)

    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="✅ Закончить")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    await message.answer(
        "Ок. Пришли файлы (документы/фото/видео/аудио и т.п.), "
        "а я в ответ буду отправлять их file_id.\n\n"
        "Когда закончишь — нажми «✅ Закончить».",
        reply_markup=kb,
    )


@admin_menu_router.message(AdminWaitFiles.waiting_files, F.text == "✅ Закончить", IsAdmin())
async def admin_files_finish(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Готово. Вышел из режима ожидания файлов.", reply_markup=types.ReplyKeyboardRemove())


@admin_menu_router.message(AdminWaitFiles.waiting_files, IsAdmin())
async def admin_files_catch(message: types.Message, state: FSMContext):
    file_ids = _extract_file_ids(message)

    if not file_ids:
        await message.answer("Не вижу файла в сообщении. Пришли документ/фото/видео/аудио и т.п.")
        return

    lines = ["Вот file_id:"]
    for kind, fid in file_ids:
        lines.append(f"- {kind}: {fid}")

    await message.answer("\n".join(lines))


@admin_menu_router.message(Command('admin'), IsAdmin())
async def start_menu(message: types.Message, state: FSMContext):
    await message.answer(
        text=templates.texts.admin_message,
        reply_markup=kb.reply.main_admin
    )


@admin_menu_router.message(F.text==templates.button_texts.admin_promocodes_button, IsAdmin())
async def start_menu(message: types.Message, state: FSMContext):
    async with db.get_session() as session:
        promocode_repo = PromocodeRepository(session)
        promocodes = await promocode_repo.get_all_promocodes(count=False)

    await message.answer(
        text=templates.texts.admin_promocodes_message,
        reply_markup=kb.inline.admin_promocodes(
            promocodes=promocodes,
            raw=0
        )
    )


@admin_menu_router.callback_query(F.data.startswith('get_transfer_history:'), IsAdmin())
async def get_transfer_history(call: types.CallbackQuery, state: FSMContext):
    user_id = int(call.data.split(':')[1]) 
    
    async with db.get_session() as session:
        action_history_repo = ActionHistoryRepository(session)
        
        # Получаем все переводы, которые получил этот пользователь
        transfers = await action_history_repo.get_user_received_transfers(user_id, limit=100)
        total_count = len(transfers)
        
        if not transfers:
            await call.message.edit_text(
                text=f"📊 История полученных переводов пользователя {user_id}\n\n❌ Переводов не найдено",
                parse_mode='HTML'
            )
            await call.answer()
            return
        
        # Считаем статистику
        total_amount = 0
        suspicious_count = 0
        suspicious_amount = 0
        
        # Формируем список последних переводов
        transfers_text = []
        
        for transfer in transfers[:15]:  # Показываем последние 15
            details = transfer.details
            amount = details.get('amount', 0)
            total_amount += amount
            
            # Проверяем подозрительность
            is_suspicious = details.get('is_same_ref', False)
            if is_suspicious:
                suspicious_count += 1
                suspicious_amount += amount
            
            # Форматируем запись - показываем кто ОТПРАВИЛ получателю
            sender_info = details.get('sender', {})
            timestamp = transfer.created_at.strftime("%d.%m %H:%M")
            emoji = "⚠️" if is_suspicious else "✅"
            
            transfers_text.append(
                f"{emoji} {timestamp} | "
                f"От пользователя {sender_info.get('user_id', '?')} → "
                f"{amount:.2f}⭐️"
            )
        
        # Формируем сообщение
        message = f"📊 История полученных переводов пользователя {user_id}\n\n"
        message += f"📈 Всего получено: {total_count} переводов на {total_amount:.2f}⭐️\n"
        message += f"⚠️ Подозрительных получено: {suspicious_count} на {suspicious_amount:.2f}⭐️\n\n"
        message += "Последние полученные переводы:\n" + "\n".join(transfers_text)
        
        if total_count > 15:
            message += f"\n\n... и еще {total_count - 15} переводов"
        
        await call.message.answer(
            text=message,
            parse_mode='HTML'
        )
    await call.answer()

@admin_menu_router.callback_query(F.data.startswith('promocodes:'), IsAdmin())
async def promocode_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()

    action = call.data.split(':')[1]
    promocode_id = int(call.data.split(':')[2])
    raw = int(call.data.split(':')[3])

    if action == 'create':
        await call.message.edit_text(
            text=templates.texts.admin_promocodes_create_message,
            reply_markup=kb.inline.cancel_kb()
        )
        return await state.set_state(PromocodeState.get_settings)

    async with db.get_session() as session:
        promocode_repo = PromocodeRepository(session)

        if action == 'delete':
            await promocode_repo.delete_promocode(promo_id=promocode_id)
            promocodes = await promocode_repo.get_all_promocodes(count=False)
            await call.answer('🗑')
            return await call.message.edit_reply_markup(
                reply_markup=kb.inline.admin_promocodes(
                    promocodes=promocodes,
                    raw=raw
                )
            )

        if action == 'status':      
            promocode = await promocode_repo.get_promocode(promocode_id=promocode_id)

            await promocode_repo.update_promocode(promocode_id=promocode_id, status=not promocode.status)

            if not promocode:
                return await call.message.answer(text=templates.texts.error_message)
            
            promocodes = await promocode_repo.get_all_promocodes(count=False)
    
            return await call.message.edit_reply_markup(
                reply_markup=kb.inline.admin_promocodes(
                    promocodes=promocodes,
                    raw=raw
                )
            )

@admin_menu_router.message(
    StateFilter(PromocodeState.get_settings),
    IsAdmin()
)
async def get_promocode_settings(message: types.Message, state: FSMContext):
    settings_data = message.text.split('\n')

    try:
        code = settings_data[0]
        activations = settings_data[1]
        amount = settings_data[2]
    except:
        await state.clear()
        return await message.answer(text=templates.texts.error_message)

    async with db.get_session() as session:
        promocode_repo = PromocodeRepository(session)
        await promocode_repo.create_promocode(
            code=code,
            activations=int(activations),
            amount=int(amount)
        )

        await state.clear()
        return await message.answer('✅')


@admin_menu_router.callback_query(F.data.startswith('promocode_swipe:'), IsAdmin())
async def promocodes_swiper(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    async with db.get_session() as session:
        promocode_repo = PromocodeRepository(session)
        promocodes = await promocode_repo.get_all_promocodes(count=False)

    raw = int(call.data.split(':')[-1])
    await call.message.edit_reply_markup(
        reply_markup=kb.inline.admin_promocodes(
            promocodes=promocodes,
            raw=raw
        )
    )
