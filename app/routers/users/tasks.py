import asyncio
import json
from app.routers.start import send_main_menu
import config
import copy

from contextlib import suppress

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter

from flyerapi.flyerapi import APIError

from loader import bot

from app.database.models.subsribes import Subscribe
from app.database.repositories.subscribe_repo import SubscribeRepository, SubscriptionHistoryRepository
from app import keyboards as kb
from app.database.repositories.user_repo import UserRepository
from app.database.models.user import User

from app.templates.texts import (
    tasks_empty_message,
    tasks_message,
    tasks_already_complete,
    tasks_complete_message,
)
from app.filters import IsPrivate
from app.database import db, flyer, redis_pool
from app.keyboards.inline import tasks_kb, back_kb, tasks_flyer_kb, tasks_subgram_kb
from app.utils.utils import check_for_bot, check_subscribe_channel
from op.services import op_service
from op.services.op_service import op_client, SubscribeModel

get_tasks_router = Router(name='get_tasks_router')

async def get_subgram_tasks(
    user_id: int,
    language_code: str,
    call: types.CallbackQuery,
    state: FSMContext,
):
    subgram_data = await op_client.fetch_subgram(max_op=10, user_id=user_id)
    
    if not subgram_data:
        return False

    sponsors = [sub for sub in subgram_data if sub['status'] == 'unsubscribed']

    cache_data = {
        'subgram_tasks': {
            'sponsors_count': len(sponsors),
            'sponsors': sponsors 
        }
    }
    await state.set_data(cache_data)
    await call.message.edit_caption(
        caption=tasks_message,
        reply_markup=tasks_subgram_kb(sponsors)
    )
    return True

@get_tasks_router.callback_query(F.data=='check_subgram_tasks', IsPrivate())
async def check_subgram_tasks(call: types.CallbackQuery, state: FSMContext, user: User):
    user_id = call.from_user.id
    subgram_tasks = (await state.get_data()).get('subgram_tasks', None)

    if not subgram_tasks:
        await state.clear()
        with suppress(TelegramBadRequest):
            await call.message.edit_caption(
                caption=tasks_empty_message
            )
            return
        return await send_main_menu(call.message)

    cached_sponsors_list = subgram_tasks.get('sponsors', [])
    remaining_tasks = []
    completed_tasks_count = 0
    top_up_balance_value = 0

    # Получаем актуальные статусы подписок
    subgram_data = await op_client.fetch_subgram(len(cached_sponsors_list), user_id)
    actual_statuses = {sponsor['link']: sponsor['status'] for sponsor in subgram_data}
    
    # Проверяем каждый кэшированный спонсор
    for cached_sponsor in cached_sponsors_list:
        link = cached_sponsor['link']
        
        if link in actual_statuses and actual_statuses[link] == 'subscribed':
            # Задание выполнено - начисляем вознаграждение
            completed_tasks_count += 1
            top_up_balance_value += config.COST_PER_TASK
        else:
            # Задание не выполнено - добавляем в оставшиеся
            remaining_tasks.append(cached_sponsor)

    # Начисляем вознаграждение за выполненные задания
    if completed_tasks_count > 0:
        async with db.get_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_user(
                user_id=user_id,
                important_action=True,
                balance=user.balance + top_up_balance_value
            )
        await call.answer(text=tasks_complete_message.format(top_up_balance_value=top_up_balance_value))

    if completed_tasks_count == 0:
        return await call.answer()

    # Обновляем кэш с оставшимися заданиями
    if remaining_tasks:
        cache_data = {
            'subgram_tasks': {
                'sponsors_count': len(remaining_tasks),
                'sponsors': remaining_tasks
            }
        }
        await state.set_data(cache_data)
        
        # Обновляем сообщение с новым списком заданий
        return await call.message.edit_caption(
            caption=tasks_message,
            reply_markup=tasks_subgram_kb(remaining_tasks)
        )
    else:
        with suppress(TelegramBadRequest):
            await call.message.edit_caption(
                    caption=tasks_empty_message,
                    reply_markup=back_kb(
                        calldata='main_menu',
                        text='⬅️ В главное меню'
                    ),
                )
        return await send_main_menu(call.message)

async def get_flyer_tasks(
    user_id: int,
    language_code: str,
    call: types.CallbackQuery,
    state: FSMContext,
):
    flyer_tasks = await flyer.get_tasks(
        user_id=user_id,
        language_code=language_code,
        limit=10,
    ) or []

    flyer_tasks = [task for task in flyer_tasks if task.get('status') == 'incomplete']

    if not flyer_tasks:
        return False

    await state.set_data({'flyer_tasks': flyer_tasks})

    await call.message.edit_caption(
        caption=tasks_message,
        reply_markup=tasks_flyer_kb(flyer_tasks)
    )
    return True
    
async def send_partners_tasks(
    user_id: int,
    language_code: str,
    call: types.CallbackQuery,
    state: FSMContext,
):
    # # Задания флаера
    async with redis_pool.get_connection() as conn:

    #     if not await conn.exists(f'skip_flyer:{user_id}') and \
    #     await get_flyer_tasks(user_id, language_code, call, state):
    #         return

    # Задания сабграма
        if not await conn.exists(f'skip_subgram:{user_id}') and \
        await get_subgram_tasks(user_id, language_code, call, state):
            return

    with suppress(TelegramBadRequest):
        return await call.message.edit_caption(
                caption=tasks_empty_message,
                reply_markup=back_kb(
                    calldata='main_menu',
                    text='⬅️ В главное меню'
                ),
            )
    return await send_main_menu(call.message)

@get_tasks_router.callback_query(F.data=='skip_flyer_web', IsPrivate(),)
@get_tasks_router.callback_query(F.data=='skip_flyer', IsPrivate(),)
async def skip_flyer_func(call: types.CallbackQuery, state: FSMContext, user: User):

    async with redis_pool.get_connection() as conn:

        if call.data == 'skip_flyer_web':
            await conn.delete(f'flyer_web_data:{user.user_id}')

        await conn.set(f'{call.data}:{user.user_id}', 1, ex=10)
    
    return await send_partners_tasks(
        user_id=user.user_id,
        language_code=call.from_user.language_code,
        call=call,
        state=state
    )


@get_tasks_router.callback_query(F.data=='tasks', IsPrivate())
async def get_stars(call: types.CallbackQuery, state: FSMContext, user: User):

    await state.clear()

    user_id = user.user_id

    await call.message.edit_media(
        media=types.InputMediaPhoto(
            media=config.TASKS_MAIN_MENU_ID,
        )
    )

    async with db.get_session() as session:
        subscribe_repo = SubscribeRepository(session)
        tasks = await subscribe_repo.get_active_tasks(user_id=user_id)

    if not tasks:

        return await send_partners_tasks(
            user_id=user.user_id,
            language_code=call.from_user.id,
            call=call,
            state=state
        )

    subbed: list[Subscribe] = []
    tasks_to_pre_check: list[Subscribe] = [task for task in tasks if task.access]

    coroutines = [
        check_for_bot(user_id, sub)
        if sub.is_bot
        else check_subscribe_channel(user_id, sub) for sub in tasks_to_pre_check
    ]
    results = await asyncio.gather(*coroutines)
    subbed.extend([sub[1] for sub in results if sub[0] is None])

    # Если уже был подписан сразу кидаем и не выдаём звезды
    if subbed:
        tasks = [task for task in tasks if task not in subbed]
        async with db.get_session() as session:
            history_repo = SubscriptionHistoryRepository(session)
            subscribe_repo = SubscribeRepository(session)

            for sub in subbed:
                await history_repo.create_subscription_history(
                    user_id=user_id,
                    sub_id=sub.id
                )
                await subscribe_repo.update_subscribe(
                    sub_id=sub.id,
                    subscribed_count=sub.subscribed_count + 1
                )
    
    if not tasks:

        return await send_partners_tasks(
            user_id=user.user_id,
            language_code=call.from_user.id,
            call=call,
            state=state
        )

    return await call.message.edit_caption(
        caption=tasks_message,
        reply_markup=tasks_kb(tasks)
    )

@get_tasks_router.callback_query(F.data=='check_flyer_tasks', IsPrivate())
async def check_flyer_tasks(call: types.CallbackQuery, state: FSMContext, user: User):
    user_id = call.from_user.id

    flyer_tasks = (await state.get_data()).get('flyer_tasks', None)
    
    if not flyer_tasks:
        await state.clear()
        with suppress(TelegramBadRequest):
            await call.message.edit_caption(
                caption=tasks_empty_message
            )
            return
        return await send_main_menu(call.message)

    completed_tasks = []
    remaining_tasks = []
    top_up_balance_value = 0

    for task in flyer_tasks:
        status = await flyer.check_task(
            user_id=user_id,
            signature=task['signature']
        )
        
        if status == 'incomplete':
            remaining_tasks.append(task)
        else:
            completed_tasks.append(task)
            top_up_balance_value += 0.25

    if completed_tasks:
        async with db.get_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_user(
                user_id=user_id,
                important_action=True,
                balance=user.balance + top_up_balance_value
            )
        await call.answer(text=tasks_complete_message.format(top_up_balance_value=top_up_balance_value))

    if not completed_tasks:
        return await call.answer()

    if not remaining_tasks:
        return await send_partners_tasks(
            user_id=user.user_id,
            language_code=call.from_user.language_code,
            call=call,
            state=state
        )

    await state.update_data({'flyer_tasks': remaining_tasks})

    with suppress(TelegramBadRequest):
        await call.message.edit_caption(
            caption=tasks_message,
            reply_markup=tasks_flyer_kb(remaining_tasks)
        )
        return
    return await send_main_menu(call.message)

@get_tasks_router.callback_query(F.data=='check_tasks', IsPrivate())
async def check_tasks(call: types.CallbackQuery, state: FSMContext, user: User):
    await state.clear()

    user_id = call.from_user.id

    async with db.get_session() as session:
        subscribe_repo = SubscribeRepository(session)
        tasks = await subscribe_repo.get_active_tasks(user_id=user_id)

    if not tasks:
        return await call.message.edit_caption(
            caption=tasks_already_complete,
            reply_markup=kb.inline.cancel_kb()
        )

    subbed: list[Subscribe] = []

    coroutines = [check_for_bot(user_id, sub) if sub.is_bot else check_subscribe_channel(user_id, sub) for sub in tasks]
    results = await asyncio.gather(*coroutines)
    subbed.extend([sub[1] for sub in results if sub[0] is None])

    remaining_tasks = [task for task in tasks if task not in subbed]

    if not remaining_tasks:
        async with db.get_session() as session:
            history_repo = SubscriptionHistoryRepository(session)
            subscribe_repo = SubscribeRepository(session)
            user_repo = UserRepository(session)
            
            top_up_balance_value = 0

            for sub in subbed:
                await history_repo.create_subscription_history(
                    user_id=user_id,
                    sub_id=sub.id
                )
                await subscribe_repo.update_subscribe(
                    sub_id=sub.id,
                    subscribed_count=sub.subscribed_count + 1
                )
                top_up_balance_value += config.COST_PER_TASK

            await user_repo.update_user(
                user_id=user_id,
                important_action=True,
                balance=user.balance + top_up_balance_value
            )

        if top_up_balance_value:
            await call.answer(text=tasks_complete_message.format(top_up_balance_value=top_up_balance_value))

        with suppress(TelegramBadRequest):
            await call.message.edit_caption(
                caption=tasks_empty_message,
                reply_markup=back_kb(
                    calldata='main_menu',
                    text='⬅️ В главное меню'
                ),
            )
            return
        return await send_main_menu(call.message)

    with suppress(TelegramBadRequest):
        await call.message.edit_caption(
            caption=tasks_message,
            reply_markup=tasks_kb(remaining_tasks)
        )
        return
    return await send_main_menu(call.message)

