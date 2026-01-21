import json

from app import templates
from app import keyboards as kb
from app import templates
from app.filters import IsAdmin
from app.pydantic_models.mailing import MailingData
from app.states.mailing import MailingState
from app.utils.mailing import Mailer

from aiogram import types, Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext


admin_mailing_router = Router(name='admin_mailing_router')

@admin_mailing_router.message(
        F.text==templates.button_texts.admin_mailings_button,
        IsAdmin(),
        StateFilter('*')
)
async def start_menu(message: types.Message, state: FSMContext):
    await state.clear()

    await message.answer(
        text=templates.texts.admin_mailing_message,
        reply_markup=kb.inline.cancel_kb()
    )

    return await state.set_state(MailingState.get_message)

@admin_mailing_router.message(
    F.content_type.in_(
        [F.text, F.photo, F.document, F.animation, F.video,]
    ),
    StateFilter(MailingState.get_message),
    IsAdmin()
)
async def get_message(message: types.Message, state: FSMContext):
    state_data = {
        'message_id': message.message_id,
        'from_chat_id': message.from_user.id,
        'reply_markup': json.loads(message.reply_markup.model_dump_json()) if message.reply_markup else None,
        'is_vip': False,
        'is_premium': False,
        'is_chats': False,
        'is_pin': False
    }
    await state.set_state(MailingState.get_filters)
    await state.set_data(data=state_data)
    await message.answer(
        text=templates.texts.admin_mailing_filters_message,
        reply_markup=kb.inline.admin_mailing_filters_kb(state_data)
    )

@admin_mailing_router.callback_query(
    StateFilter(MailingState.get_filters),
    IsAdmin()
)
async def mailing_filters_settings(call: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    action = call.data.split(':')[-1]

    if action == 'continue':
        await call.message.delete()
        await state.set_state(MailingState.pre_check)
        await call.message.bot.copy_message(
            chat_id=call.from_user.id,
            from_chat_id=state_data['from_chat_id'],
            message_id=state_data['message_id'],
            reply_markup=state_data['reply_markup']
        )
        await state.set_state(MailingState.start_mailing)
        return await call.message.answer(
            text=templates.texts.admin_mailing_pre_check_message,
            reply_markup=kb.inline.admin_mailing_pre_check_kb()
        )
        
    
    state_data[action] = not state_data[action]

    await state.update_data(data=state_data)
    return await call.message.edit_reply_markup(
        reply_markup=kb.inline.admin_mailing_filters_kb(state_data)
    )

@admin_mailing_router.callback_query(
    StateFilter(MailingState.start_mailing),
    IsAdmin()
)
async def start_mailing(call: types.CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    await call.message.delete()
    await state.clear()
    
    mailer = Mailer(
        bot=call.message.bot,
        data=MailingData(**state_data)
    )

    return await mailer.mail()
