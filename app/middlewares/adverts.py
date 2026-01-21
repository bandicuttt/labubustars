import asyncio
import time

import aiohttp
import config

from app.database import repositories, db, redis_pool
from app.database.models import Advert
from app.logger import logger
from app.middlewares.subscribes import EXPLICITLY_HANDLED_CALLBACKS
from app.utils.gift_miner import LOTTERY_CB_PREFIX, CB_MORE
from app.routers.users.gift_miner import VERIFY_CB
from app.utils.utils import get_admins
from app.templates import texts
from app.utils.advert_service import adverts_client

from loader import bot

from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware, types
from aiogram.types import Update


ADVERT_INACTIVITY_SECONDS = 60*4


class AdvertMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self._inactivity_tasks: Dict[int, asyncio.Task] = {}

    async def _mark_user_active(self, user_id: int, timestamp: int) -> None:
        key = f"last_active:{user_id}"
        async with redis_pool.get_connection() as redis:
            await redis.set(key, timestamp, ex=ADVERT_INACTIVITY_SECONDS * 4)

    def _schedule_inactivity_task(self, user_id: int, last_seen: int) -> None:
        old_task = self._inactivity_tasks.pop(user_id, None)
        if old_task:
            old_task.cancel()

        task = asyncio.create_task(self._wait_for_inactivity(user_id, last_seen))
        self._inactivity_tasks[user_id] = task

        def _cleanup(fut: asyncio.Future, uid: int = user_id) -> None:
            if self._inactivity_tasks.get(uid) is fut:
                self._inactivity_tasks.pop(uid, None)

        task.add_done_callback(_cleanup)

    async def _wait_for_inactivity(self, user_id: int, last_seen: int) -> None:
        try:
            await asyncio.sleep(ADVERT_INACTIVITY_SECONDS)

            key = f"last_active:{user_id}"
            async with redis_pool.get_connection() as redis:
                stored_last_active = await redis.get(key)

            try:
                stored_last_active_int = int(stored_last_active) if stored_last_active is not None else None
            except (TypeError, ValueError):
                stored_last_active_int = None

            if stored_last_active_int is not None and stored_last_active_int > last_seen:
                # Пользователь снова активен — не запускаем рассылку
                return

            asyncio.create_task(adverts_client.start_advert_spam(user_id))
            print(f"spam started for {user_id}")


        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Error scheduling advert spam for user {user_id}: {exc}", exc_info=True)

    async def __call__(
        self, 
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        event_user: Optional[types.User] = data.get("event_from_user")
        
        message = event.message or (event.callback_query and event.callback_query.message)
        event_chat: Optional[types.Chat] = data.get("event_chat") or (message.chat if message else None)

        if not event_user \
        or event.chat_join_request \
        or event_user.is_bot \
        or not getattr(event_chat, 'type', None) == 'private' \
        or event_user.id in get_admins():
            return await handler(event, data)
        
        allowed = True
        if event.callback_query:
            if event.callback_query and event.callback_query.data == VERIFY_CB:
                allowed = False
        if message and allowed:
            print(f"ADVERT TRY SENT TO {event_user.id}")
            await adverts_client.send(event_user.id, message)

        timestamp = int(time.time())
        await self._mark_user_active(event_user.id, timestamp)
        self._schedule_inactivity_task(event_user.id, timestamp)

        return await handler(event, data)
