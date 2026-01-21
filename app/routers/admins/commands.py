from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

from app.database import db
from app.database.repositories import AdvertHistoryRepository
from app.filters import IsAdmin

admin_commands_router = Router(name='admin_commands_router')


@admin_commands_router.message(F.text.startswith('/set_channel'), IsAdmin())
async def set_channel(message: types.Message, state: FSMContext):
    await state.clear()

    try:
        url = message.text.split(' ')[1]
    except IndexError:
        return await message.answer(texts.error_set_channel_command)

    async with redis_pool.get_connection() as con:
        await con.set('channel', value=url)

    await message.answer('✅')


@admin_commands_router.message(F.text.startswith('/clear_jackpot'), IsAdmin())
async def set_channel(message: types.Message, state: FSMContext):
    await state.clear()

    async with redis_pool.get_connection() as con:
        await con.set('jackpot', value=0)

    await message.answer('✅')


from aiogram.fsm.context import FSMContext
from aiogram import Router, F, types
from aiogram.filters import Command

from app.filters import IsAdmin
from app.templates import texts
from app.database import redis_pool
from app.utils.lottery_helper import LOTTERY_SEEN_KEY

admin_commands_router = Router(name='admin_commands_router')


@admin_commands_router.message(F.text.startswith('/set_channel'), IsAdmin())
async def set_channel(message: types.Message, state: FSMContext):
    await state.clear()

    try:
        url = message.text.split(' ')[1]
    except IndexError:
        return await message.answer(texts.error_set_channel_command)

    async with redis_pool.get_connection() as con:
        await con.set('channel', value=url)

    await message.answer('✅')


@admin_commands_router.message(F.text.startswith('/clear_jackpot'), IsAdmin())
async def set_channel(message: types.Message, state: FSMContext):
    await state.clear()

    async with redis_pool.get_connection() as con:
        await con.set('jackpot', value=0)

    await message.answer('✅')


@admin_commands_router.message(Command("reset_lottery"), IsAdmin())
async def reset_lottery_flag(message: types.Message):
    """
    Команда: /reset_lottery <user_id>
    Сбрасывает флаг "лотерея уже показана" для указанного пользователя.
    """
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❗ Укажи user_id.\nПример: /reset_lottery 123456789")
        return

    try:
        user_id = int(args[1].strip())
    except ValueError:
        await message.answer("❗ Некорректный user_id (должен быть числом).")
        return

    async with redis_pool.get_connection() as conn:
        key = LOTTERY_SEEN_KEY.format(user_id=user_id)
        deleted = await conn.delete(key)

    if deleted:
        await message.answer(f"✅ Флаг лотереи для пользователя <code>{user_id}</code> сброшен.")
    else:
        await message.answer(f"ℹ️ Флаг для <code>{user_id}</code> не найден (уже сброшен или не устанавливался).")


@admin_commands_router.message(Command("reset_advs"), IsAdmin())
async def reset_adverts_history(message: types.Message):
    """
    Команда: /reset_advs <user_id>
    Сбрасывает историю показов рекламы (redis + adverts_history) для пользователя.
    """
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❗ Укажи user_id.\nПример: /reset_advs 123456789")
        return

    try:
        user_id = int(args[1].strip())
    except ValueError:
        await message.answer("❗ Некорректный user_id (должен быть числом).")
        return

    async with redis_pool.get_connection() as conn:
        pattern = f"advert:*:user:{user_id}:*"
        keys = [key async for key in conn.scan_iter(match=pattern)]
        deleted_keys = 0
        if keys:
            deleted_keys = await conn.delete(*keys)

    async with db.get_session() as session:
        history_repo = AdvertHistoryRepository(session)
        deleted_rows = await history_repo.delete_by_user_id(user_id)

    await message.answer(
        "✅ История показов очищена.\n"
        f"Redis ключей удалено: <code>{deleted_keys}</code>\n"
        f"Записей в БД удалено: <code>{deleted_rows}</code>"
    )

