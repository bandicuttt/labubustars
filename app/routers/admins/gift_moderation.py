from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from app.database import db, redis_pool
from app.database.repositories import UserRepository
from app.filters.admin import IsAdmin
from app.keyboards import inline


gift_moderation_router = Router(name="gift_moderation_router")


@gift_moderation_router.callback_query(F.data.startswith("gift_ban:"), IsAdmin())
async def toggle_gift_ban(call: types.CallbackQuery, state: FSMContext):
    await state.clear()

    _, user_id_raw = call.data.split(":")
    user_id = int(user_id_raw)

    async with db.get_session() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_user(user_id=user_id)
        if not db_user:
            await call.answer("Пользователь не найден", show_alert=True)
            return
        new_status = not db_user.banned
        await user_repo.update_user(user_id=user_id, banned=new_status)

    async with redis_pool.get_connection() as redis:
        await redis.delete(f"user:{user_id}")

    await call.message.edit_reply_markup(reply_markup=inline.gift_ban_kb(user_id, new_status))
    await call.answer()
