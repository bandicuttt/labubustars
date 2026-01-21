from pydantic.type_adapter import P

from loader import bot
from config import MEDIA_DIR, BOT_USERNAME, TASKS_MAIN_MENU_ID

from datetime import timedelta
from app.utils.misc_function import get_time_now

from app import templates
from app.filters import IsAdmin
from app import keyboards as kb
from app.database import db
from app.database.repositories import SubscribeRepository
from app.states.subscribes import SubscribeState
from app.database.models import Subscribe, User
from app.templates.texts import bot_permisson_error, push_notification_new_subscription_message

from aiogram import types, Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from app.utils.utils import is_valid_link, check_subscribe_channel


admin_subscribes_router = Router(name='admin_subscribes_router')

@admin_subscribes_router.message(F.text==templates.button_texts.admin_subscribes_button, IsAdmin())
async def start_menu(message: types.Message, state: FSMContext):
    await state.clear()
    async with db.get_session() as session:
        subscribe_repo = SubscribeRepository(session)
        subscribes = await subscribe_repo.get_all_subscribes_total(count=False)

    await message.answer(
        text=templates.texts.admin_subscribes_message,
        reply_markup=kb.inline.admin_subscribes(
            subscribes=subscribes,
            raw=0
        )
    )

@admin_subscribes_router.callback_query(F.data.startswith('subscribes:'),IsAdmin())
async def subscribe_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()

    action = call.data.split(':')[1]
    sub_id = int(call.data.split(':')[2])
    raw = int(call.data.split(':')[3])

    if action == 'create':
        await state.set_state(SubscribeState.get_subscribe_type)
        return await call.message.edit_text(
            text=templates.texts.admin_create_subscribe_message,
            reply_markup=kb.inline.admin_subscribe_type_kb()
        )

    async with db.get_session() as session:
        subscribe_repo = SubscribeRepository(session)

        if action == 'delete':
            await subscribe_repo.delete_subscribe(sub_id=sub_id)
            subscribes = await subscribe_repo.get_all_subscribes_total(count=False)
            await call.answer('🗑')
            return await call.message.edit_reply_markup(
                reply_markup=kb.inline.admin_subscribes(
                    subscribes=subscribes,
                    raw=raw
                )
            )

        if action == 'status':
            sub = await subscribe_repo.get_subscribe(sub_id=sub_id)

            await subscribe_repo.update_subscribe(sub_id=sub_id, status=not sub.status)

            if not sub:
                return await call.message.answer(text=templates.texts.error_message)
            
            subscribes = await subscribe_repo.get_all_subscribes_total(count=False)
    
            return await call.message.edit_reply_markup(
                reply_markup=kb.inline.admin_subscribes(
                    subscribes=subscribes,
                    raw=raw
                )
            )
        
@admin_subscribes_router.callback_query(
    F.data.startswith('subscribes_create:'),
    StateFilter(SubscribeState.get_subscribe_type)
)
async def create_subscribe(call: types.CallbackQuery, state: FSMContext):
    state_data = {
        'is_check': True if call.data.split(':')[-1] == 'check_true' else False
    }

    await state.set_state(SubscribeState.get_subscribe_data)
    await state.set_data(data=state_data)
    await call.message.edit_text(
        text=templates.texts.admin_create_subscribe_check_data_message if state_data['is_check'] \
        else templates.texts.admin_create_subscribe_data_message,
        reply_markup=kb.inline.cancel_kb()
    )

@admin_subscribes_router.message(StateFilter(SubscribeState.get_subscribe_data))
async def create_subscribe_data(message: types.Message, state: FSMContext):
    is_check = (await state.get_data())['is_check']
    settings_data = message.text.split('\n')
    await state.clear()

    try:
        title = settings_data[0]
        is_task = True if settings_data[1] == '0' else False
        url = settings_data[2]
        subscribe_count = int(settings_data[3])
        access = None

        if is_check:
            access = settings_data[4]
            send_push = False  # True if settings_data[5] == '1' else False
        else:
            send_push = False  # True if settings_data[4] == '1' else False

        if not is_valid_link(text=url):
            return await message.answer(text=templates.texts.error_message)
    except:
        return await message.answer(text=templates.texts.error_message)
    
    is_bot = True if 'tgbot' in url.lower() or 'bot' in url.lower() else False

    async with db.get_session() as session:
        subscribe_repo = SubscribeRepository(session)
        sub = await subscribe_repo.create_subscribe(
            access=access,
            is_bot=is_bot,
            title=title,
            url=url,
            subscribe_count=subscribe_count,
            is_task=is_task
        )
    
    await state.clear()

    if not is_bot:
        bot_status = (await check_subscribe_channel(
            user_id=message.bot.id,
            sub=sub
        ))[0]

        if bot_status is not None:
            async with db.get_session() as session:
                subscribe_repo = SubscribeRepository(session)
                await subscribe_repo.update_subscribe(sub_id=sub.id, status=False)
            return await message.answer(bot_permisson_error)
    
    await message.answer('✅')

    if not send_push:
        return
    good = bad = 0

    async with db.get_session() as session:

        threshold_time = get_time_now() - timedelta(hours=24)

        async with db.get_session() as session:
            query = await session.execute(
                select(User)
                .where(User.last_activity < threshold_time)
            )
        users_to_notify: list[User] = query.scalars().all()

        for user in users_to_notify:

            try:
                await bot.send_photo(
                    photo=TASKS_MAIN_MENU_ID,
                    chat_id=user.user_id,
                    caption=push_notification_new_subscription_message,
                    reply_markup=kb.inline.push_notification_kb(
                        BOT_USERNAME,
                        user.user_id
                    )
                )
                good+=1
            except Exception as e:
                bad+=1

    await message.answer(f'''
Пуши отправлены!

Доставлено: {good}
Заблокировано: {bad}
    ''')


@admin_subscribes_router.callback_query(F.data.startswith('subscribes_swipe:'),IsAdmin())
async def subscribe_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    async with db.get_session() as session:
        subscribe_repo = SubscribeRepository(session)
        subscribes = await subscribe_repo.get_all_subscribes_total(count=False)

    raw = int(call.data.split(':')[-1])
    await call.message.edit_reply_markup(
        reply_markup=kb.inline.admin_subscribes(
            subscribes=subscribes,
            raw=raw
        )
    )
