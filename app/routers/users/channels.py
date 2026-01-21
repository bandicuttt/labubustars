from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext

from app.routers.start import send_main_menu
from app.filters import IsPrivate
from app import templates
from app.database import redis_pool
from app.keyboards.inline import out_channel_kb


channel_router = Router(name='channel_router')

@channel_router.message(F.text==templates.button_texts.users_get_channel_button, IsPrivate())
async def out_channel(message: types.Message, state: FSMContext):
    await state.clear()

    async with redis_pool.get_connection() as con:
        channel = await con.get('channel')

        if not channel:
            channel = 'https://google.com'
        else:
            channel = str(channel.decode('utf-8'))

    await message.answer_photo(
        photo=types.FSInputFile('app/static/our_channel.jpg'),
        caption=templates.texts.out_channel_message.format(
            channel_url=channel
        ),
        reply_markup=out_channel_kb(channel)
    )

