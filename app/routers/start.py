from aiogram import types, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

import config
from app import templates
from app.database import db
from app.database.models import User
from app.database.repositories.bot_settings import SettingsRepository
from app.filters import IsPrivate
from app.keyboards.inline import games_main_menu
from app.keyboards.inline import main_user, pseudo_gift_kb
from app.templates.texts import user_games_main_message

start_router = Router(name='start_router')


async def send_main_menu(message: types.Message):
    await message.answer_photo(
        photo=config.MAIN_MENU_ID,
        caption=templates.texts.start_message,
        reply_markup=main_user()
    )


@start_router.callback_query(F.data == 'main_menu', IsPrivate(), StateFilter('*'))
async def start_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await send_main_menu(call.message)


LOCAL_PHOTO_CACHE = {}


async def send_pseudo_gift(msg: types.Message):
    async with db.get_session() as session:
        settings_repo = SettingsRepository(session)
        start_bonus_url = await settings_repo.get("START_BONUS_URL")
    mkp = pseudo_gift_kb(start_bonus_url=start_bonus_url)

    photo = LOCAL_PHOTO_CACHE.get("darts_start")
    txt = "<b>🎣Поймай мишку!🧸</b>"

    if photo:
        # Отправляем по file_id
        await msg.answer_photo(
            photo=photo,
            caption=txt,
            reply_markup=mkp,
            link_preview_options=types.LinkPreviewOptions(is_disabled=True)
        )
        return

    # --- Если file_id еще нет — загружаем файл с диска ---
    img_path = 'app/static/cheba_fishing.jpg'
    photo_file = types.FSInputFile(img_path)
    message = await msg.answer_photo(
        photo=photo_file,
        caption=txt,
        reply_markup=mkp,
        link_preview_options=types.LinkPreviewOptions(is_disabled=True)
    )

    # --- сохраняем file_id для будущего использования ---
    try:
        LOCAL_PHOTO_CACHE["darts_start"] = message.photo[-1].file_id
    except Exception as e:
        print("Не смог сохранить file_id:", e)


@start_router.message(Command('start'), IsPrivate(), StateFilter('*'))
async def start_menu(message: types.Message | types.CallbackQuery, state: FSMContext, ref: str | None, user: User):
    await state.clear()
    if ref == 'jackpot':
        return await message.answer_photo(
            photo=config.GAMES_MENU_ID,
            caption=user_games_main_message,
            reply_markup=games_main_menu()
        )
    return await send_pseudo_gift(message)


@start_router.callback_query(F.data == 'close', IsPrivate(), StateFilter('*'))
async def start_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()

    await send_main_menu(call.message)
