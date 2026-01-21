from contextlib import suppress
import config
import json
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from annotated_types import IsDigit
from app.database.repositories import referral_repo, ReferralRepository
from app.templates import texts
from app.utils.misc_function import get_time_now
from app.utils.utils import get_ref
from app.database import repositories
from app.database import db, redis_pool
from app.database.models import User

from loader import bot

from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from aiogram import BaseMiddleware, Bot, types
from aiogram.types import Update

from sqlalchemy.ext.asyncio import AsyncSession

# Константы для Redis
CACHE_TTL = 24 * 60 * 60  # 24 часа
USER_CACHE_PREFIX = "user:"
REF_CACHE_PREFIX = "ref:"
TOTAL_REF_PREFIX = "total:"
DAILY_REF_PREFIX = "daily:"
UNIQUE_REF_PREFIX = "unique:"
DAILY_UNIQUE_PREFIX = "daily_unique:"

BAN_LIST = [7937241603, 5768061998, 8149125582, 6403645090, 6448302670, 8001338558]


class ExistsUserMiddleware(BaseMiddleware):

    @staticmethod
    async def ref_func(
        event,
        event_user,
        redis_con
    ) -> Tuple[str, Optional[str]]:
        is_ref = getattr(event.message, 'text', False)
        ref = None
        print("REF_FUNC ENTER")
        if is_ref and len(is_ref.split(' ')) == 2:
            ref = is_ref.split(' ')[1]

            key = f'ref:{ref}:{event_user.id}'
            total_key = f'total:{ref}'
            today = get_time_now().strftime("%Y-%m-%d")
            daily_key = f'daily:{ref}:{today}'
            unique_total_key = f'unique:{ref}'
            unique_daily_key = f'daily_unique:{ref}:{get_time_now().strftime("%Y-%m-%d")}'
            cooldown_key = f'ads_cooldown_user:{event_user.id}'

            allow_totals: bool = False
            is_unique: bool = False

            # --- БЛОК REDIS ---
            try:
                # Кулдаун на любые рекламные ссылки
                allow_totals = await redis_con.set(
                    cooldown_key,
                    "1",
                    ex=config.ADS_COOLDOWN,
                    nx=True
                )
                print("ALLOW_TOTALS: " + str(allow_totals))

                # Если не в кулдауне — считаем total/daily
                if allow_totals:
                    await redis_con.incr(total_key)
                    await redis_con.incr(daily_key)
                    total = await redis_con.get(total_key)
                    daily = await redis_con.get(daily_key)
                    print(f"Ref: {ref} | Total: {total} | Daily: {daily}")
                    await redis_con.expire(daily_key, 3 * 24 * 60 * 60)

                # Проверяем, был ли этот юзер уже засчитан как уникальный
                exists = await redis_con.exists(key)

                if not exists:
                    is_unique = True
                    # помечаем юзера уникальным для этой рефки
                    await redis_con.set(key, 'exist', ex=24 * 60 * 60)
                    await redis_con.incr(unique_total_key)
                    await redis_con.incr(unique_daily_key)
                    await redis_con.expire(unique_daily_key, 24 * 60 * 60)

            except Exception as e:
                print(f"Redis error: {e}")

            # --- БЛОК БД (referrals) ---
            try:
                async with db.get_session() as session:
                    ref_repo = ReferralRepository(session=session)
                    # total_visit — раз в кулдаун
                    if allow_totals:
                        await ref_repo.increment_total_visits(ref)
                    # uniq_visit — только если реально уникальный
                    if is_unique:
                        await ref_repo.increment_uniq_visits(ref)
            except Exception as e:
                print(f"Referral DB error: {e}")

        return ref


    @staticmethod
    def serialize_user(user: User) -> str:
        """Сериализация пользователя для Redis"""
        try:
            return json.dumps({
                'user_id': user.user_id,
                'user_name': user.user_name,
                'user_fullname': user.user_fullname,
                'is_premium': user.is_premium,
                'ref': user.ref,
                'banned': user.banned

            })
        except Exception as e:
            print(f"Serialization error: {e}")
            return ""

    @staticmethod
    def deserialize_user(user_data: str) -> Optional[User]:
        """Десериализация пользователя из Redis"""
        try:
            data = json.loads(user_data)
            return User(**data)
        except Exception as e:
            print(f"Deserialization error: {e}")
            return None

    async def invalidate_user_cache(self, user_id: int) -> None:
        """Инвалидация кэша пользователя"""
        try:
            async with redis_pool.get_connection() as redis:
                # Получаем все ключи, связанные с пользователем
                user_key = f"{USER_CACHE_PREFIX}{user_id}"
                await redis.delete(user_key)
        except Exception as e:
            print(f"Cache invalidation error: {e}")

    async def __call__(
        self, 
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        event_user: Optional[types.User] = data.get("event_from_user")
        event_chat: Optional[types.Chat] = data.get("event_chat")

        with suppress(TelegramForbiddenError, TelegramBadRequest):
            m = await bot.send_sticker(
                chat_id=event_user.id,
                sticker=config.LOADING_ID
            )
            data['temp'] = m.message_id

        if event_user.is_bot: return

        if not event_user \
        or event.chat_join_request \
        or not getattr(event_chat, 'type', None) == 'private':
            data['user'] = None
            data['ref'] = None
            return await handler(event, data)

        data['ref'] = None

        if event_user.id in BAN_LIST:
            return

        try:
            # Используем один коннект к Redis для всех операций
            async with redis_pool.get_connection() as redis:
                # Обработка рефералов
                ref = await self.ref_func(event, event_user, redis)
                data['ref'] = ref
                # Пробуем получить пользователя из кэша
                user_key = f"{USER_CACHE_PREFIX}{event_user.id}"

                # Проверяем тип данных перед получением
                key_type = await redis.type(user_key)
                if key_type != 'string' and key_type != 'none':
                    # Если тип неверный, удаляем ключ
                    await redis.delete(user_key)
                    cached_user = None
                else:
                    cached_user = await redis.get(user_key)

                if cached_user:
                    user = self.deserialize_user(cached_user)
                    if user:
                        if user.banned:
                            return
                        data['user'] = user
                        return await handler(event, data)

                # Если пользователя нет в кэше или произошла ошибка десериализации
                async with db.get_session() as session:
                    user_repo = repositories.UserRepository(session)
                    user = await user_repo.get_user(user_id=event_user.id)

                    if not user and not event.inline_query:
                        data['new'] = True
                        user = await user_repo.create_user(
                            user_id=event_user.id,
                            user_name=event_user.username,
                            user_fullname=event_user.full_name,
                            is_premium=event_user.is_premium or False,
                            ref=ref,
                        )

                    # Кэшируем пользователя
                    if user:
                        serialized_user = self.serialize_user(user)
                        if serialized_user:
                            # Удаляем старый ключ перед установкой нового
                            await redis.delete(user_key)
                            await redis.set(
                                user_key,
                                serialized_user,
                                ex=CACHE_TTL
                            )

                    data['user'] = user
                    if user and user.banned:
                        return

        except Exception as e:
            print(f"Middleware error: {e}")
            # В случае ошибки, пытаемся получить пользователя напрямую из БД
            async with db.get_session() as session:
                user_repo = repositories.UserRepository(session)
                user = await user_repo.get_user(user_id=event_user.id)
                data['user'] = user
                if user and user.banned:
                    return

        return await handler(event, data)

