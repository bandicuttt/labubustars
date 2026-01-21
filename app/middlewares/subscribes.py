from app.database.repositories.user_repo import UserRepository
import config
from app.utils.gift_miner import CB_MORE, LOTTERY_CB_PREFIX

from app.database import repositories, db, redis_pool
from app.database.models import User
from app.utils.utils import get_admins
from app.templates import texts

from loader import bot
from op.services.op_service import op_client

from typing import Any, Awaitable, Callable, Dict, Optional

from contextlib import suppress
from aiogram import BaseMiddleware, types
from aiogram.types import Update
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# коллбэки, которые полностью управляются своими хендлерами и не должны триггерить мидлварь
EXPLICITLY_HANDLED_CALLBACKS = {
    "get_my_gift",  # старт карты подарка
    "start_dart",  # проверка после подарка
    f"check_dart",
    "darts:check_referrals",
    CB_MORE,
    "fish:",
}


class SubscribeMiddleware(BaseMiddleware):

    async def process_referral_reward(self, user: User, event_user_id: int):

        if not user:
            return

        async with db.get_session() as session, redis_pool.get_connection() as con:
            user_repo = repositories.UserRepository(session)

            # Выставляем subbed=True
            if not user.subbed:
                await user_repo.update_user(
                    user_id=user.user_id,
                    subbed=True
                )

            ref: str | None = user.ref

            if not ref or not ref.isdigit() or int(ref) == event_user_id:
                return

            key = f'reward:{ref}:{event_user_id}'
            is_reward = await con.exists(key)

            if not is_reward:
                with suppress(TelegramForbiddenError, TelegramBadRequest):
                    await user_repo.add_user_balance_ref(user_id=int(ref))
                    await bot.send_message(
                        chat_id=ref,
                        text=texts.new_referral_message
                    )
            await con.set(key, '1')

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any],
    ) -> Any:
        event_user: Optional[types.User] = data.get("event_from_user")
        event_chat: Optional[types.Chat] = data.get("event_chat")
        user: User = data.get('user')

        if data.get('temp'):
            with suppress(TelegramForbiddenError, TelegramBadRequest):
                await bot.delete_message(
                    chat_id=event_chat.id,
                    message_id=data['temp']
                )

        if not event_user \
                or event.chat_join_request \
                or event_user.is_bot \
                or not getattr(event_chat, 'type', None) == 'private' \
                or event_user.id in get_admins():
            return await handler(event, data)

        skip_by_context = False
        for_op_ev = None

        if event.callback_query:
            for_op_ev = event.callback_query
            cbdata = event.callback_query.data or ""
            if any(cbdata.startswith(ex) for ex in EXPLICITLY_HANDLED_CALLBACKS):
                skip_by_context = True

        if event.message and event.message.text:
            for_op_ev = event.message
            txt = event.message.text
            if txt.startswith("/ref_"):
                skip_by_context = True  # рефералка сама рулит
            elif txt.startswith("/start"):
                skip_by_context = True  # старт — логика полностью в хендлере

        if not for_op_ev:
            skip_by_context = True

        if skip_by_context:
            return await handler(event, data)

        reply_markup = await op_client.check(
            user_id=for_op_ev.from_user.id,
            language_code="ru",
            message=for_op_ev,
            done_cb="check_dart",
            no_manual=True
        )

        if reply_markup:
            with suppress(TelegramForbiddenError, TelegramBadRequest):
                return await bot.send_photo(
                    photo=config.MAIN_MENU_ID,
                    chat_id=event_user.id,
                    caption=texts.subscribes_message,
                    reply_markup=reply_markup
                )
        else:
            with suppress(TelegramForbiddenError, TelegramBadRequest):
                await self.process_referral_reward(user, event_user.id)
        return await handler(event, data)


