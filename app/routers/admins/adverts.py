import json

from app import templates
from app.database.repositories.bot_settings import SettingsRepository
from app.filters import IsAdmin
from app import keyboards as kb
from app.database import db
from app.database.repositories import AdvertRepository
from app.states.adverts import AdvertState

from aiogram import types, Router, F
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext


admin_adverts_router = Router(name='admin_adverts_router')


@admin_adverts_router.message(Command('set_advert_url'), IsAdmin())
async def set_advert_url(message: types.Message):
    if not message.text or len(message.text.split(' ')) == 1:
        return await message.answer(text="Отправь ссылку в формате: /set_advert_url ссылка")
    url = message.text.split(' ')[-1]
    async with db.get_session() as session:
        settings_repo = SettingsRepository(session)
        await settings_repo.set("START_BONUS_URL", url)
        return await message.answer(text=f"Ссылка {url} установлена")


@admin_adverts_router.message(F.text==templates.button_texts.admin_adverts_button, IsAdmin())
async def start_menu(message: types.Message, state: FSMContext):
    async with db.get_session() as session:
        advert_repo = AdvertRepository(session)
        adverts = await advert_repo.get_all_adverts(count=False)

    await message.answer(
        text=templates.texts.admin_adverts_message,
        reply_markup=kb.inline.admin_adverts(
            adverts=adverts,
            raw=0
        )
    )

@admin_adverts_router.callback_query(F.data.startswith('adverts:'),IsAdmin())
async def advert_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()

    action = call.data.split(':')[1]
    advert_id = int(call.data.split(':')[2])
    raw = int(call.data.split(':')[3])

    if action == 'create':
        await call.message.edit_text(
            text=templates.texts.admin_create_advert_message,
            reply_markup=kb.inline.cancel_kb()
        )
        return await state.set_state(AdvertState.get_message)

    async with db.get_session() as session:
        advert_repo = AdvertRepository(session)

        if action == 'delete':
            await advert_repo.delete_advert(advert_id=advert_id)
            adverts = await advert_repo.get_all_adverts(count=False)
            await call.answer('🗑')
            return await call.message.edit_reply_markup(
                reply_markup=kb.inline.admin_adverts(
                    adverts=adverts,
                    raw=raw
                )
            )
            

        if action == 'show':
            advert = await advert_repo.get_advert(advert_id=advert_id)
            await call.answer('👀')
            if not advert:
                return await call.message.answer(text=templates.texts.error_message)
            
            await call.message.bot.copy_message(
                message_id=advert.message_id,
                chat_id=call.from_user.id,
                from_chat_id=advert.from_chat_id,
                reply_markup=advert.reply_markup
            )

        if action == 'status':      
            advert = await advert_repo.get_advert(advert_id=advert_id)

            await advert_repo.update_advert(advert_id=advert_id, status=not advert.status)
            await advert_repo.invalidate_adverts_cache()
            if not advert:
                return await call.message.answer(text=templates.texts.error_message)
            
            adverts = await advert_repo.get_all_adverts(count=False)
    
            return await call.message.edit_reply_markup(
                reply_markup=kb.inline.admin_adverts(
                    adverts=adverts,
                    raw=raw
                )
            )

@admin_adverts_router.message(
    F.content_type.in_(
        [F.text, F.photo, F.document, F.animation, F.video,]
    ),
    StateFilter(AdvertState.get_message),
    IsAdmin()
)
async def get_message(message: types.Message, state: FSMContext):
    state_data = {
        'message_id': message.message_id,
        'from_chat_id': message.from_user.id,
        'reply_markup': json.loads(message.reply_markup.model_dump_json()) if message.reply_markup else None,
    }
    await state.set_data(data=state_data)
    await message.answer(
        text=templates.texts.admin_create_avert_settings_message,
        reply_markup=kb.inline.cancel_kb()
    )
    await state.set_state(AdvertState.get_settings)

@admin_adverts_router.message(
    StateFilter(AdvertState.get_settings),
    IsAdmin()
)
async def get_advert_settings(message: types.Message, state: FSMContext):
    settings_data = message.text.split('\n')

    try:
        title = settings_data[0]
        uniq_filter = int(settings_data[1])
        views = int(settings_data[2])
        only_start = True if int(settings_data[3]) == 1 else False
    except:
        await state.clear()
        return await message.answer(text=templates.texts.error_message)

    state_data = await state.get_data()

    async with db.get_session() as session:
        advert_repo = AdvertRepository(session)
        advert = await advert_repo.create_advert(
            title=title,
            message_id=state_data['message_id'],
            from_chat_id=state_data['from_chat_id'],
            reply_markup=state_data['reply_markup'],
            uniq_filter=uniq_filter,
            views=views,
            only_start=only_start,
        )

        await state.clear()
        return await message.answer('✅')
    

@admin_adverts_router.callback_query(F.data.startswith('adverts_swipe:'), IsAdmin())
async def adverts_swiper(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    async with db.get_session() as session:
        advert_repo = AdvertRepository(session)
        adverts = await advert_repo.get_all_adverts(count=False)

    raw = int(call.data.split(':')[-1])
    await call.message.edit_reply_markup(
        reply_markup=kb.inline.admin_adverts(
            adverts=adverts,
            raw=raw
        )
    )
