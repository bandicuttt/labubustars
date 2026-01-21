import time
from datetime import timedelta

from aiogram import types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.database import redis_pool
from loader import bot


BOTOHUB_REWARD_SECONDS = 60 * 60 * 24
BOTOHUB_REWARD_STARS = 5
BOTOHUB_REWARD_KEY = "botohub:reward:{user_id}"
BOTOHUB_REWARD_USERS_KEY = "botohub:reward_users"
BOTOHUB_REWARD_LOCK_KEY = "botohub:reward_lock:{user_id}"


def _format_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "00:00"
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}"


def _build_reply_kb(remaining_hhmm: str | None = None) -> types.ReplyKeyboardMarkup:
    btn_text = "🎁 Награда за подписки" if not remaining_hhmm else f"🎁 Награда через {remaining_hhmm}"
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=btn_text)]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


async def _refresh_reply_keyboard(user_id: int, remaining_hhmm: str) -> None:
    try:
        m = await bot.send_message(
            chat_id=user_id,
            text=" ",
            reply_markup=_build_reply_kb(remaining_hhmm),
        )
        try:
            await m.delete()
        except (TelegramForbiddenError, TelegramBadRequest):
            return
    except (TelegramForbiddenError, TelegramBadRequest):
        return


def _build_message_text(remaining_hhmm: str) -> str:
    return (
        "🎁 Спасибо за подписки!\n\n"
        f"⚠️ Если вы не отпишетесь от каналов, то через 24 часа получите +{BOTOHUB_REWARD_STARS} ⭐️\n\n"
        f"⏳ Награда за подписки придёт через {remaining_hhmm}"
    )


async def ensure_botohub_reward_message(user_id: int) -> None:
    key = BOTOHUB_REWARD_KEY.format(user_id=user_id)

    lock_key = BOTOHUB_REWARD_LOCK_KEY.format(user_id=user_id)
    async with redis_pool.get_connection() as redis:
        got_lock = await redis.set(lock_key, 1, nx=True, ex=10)
    if not got_lock:
        return

    async with redis_pool.get_connection() as redis:
        data = await redis.hgetall(key)

    message_id_raw = data.get("message_id") if isinstance(data, dict) else None
    if message_id_raw is None:
        message_id_raw = data.get(b"message_id")

    unlock_at_raw = data.get("unlock_at") if isinstance(data, dict) else None
    if unlock_at_raw is None:
        unlock_at_raw = data.get(b"unlock_at")

    # Если таймер уже активен — НИЧЕГО не сбрасываем и не запускаем повторно.
    if unlock_at_raw is not None:
        try:
            unlock_at = int(unlock_at_raw.decode() if isinstance(unlock_at_raw, (bytes, bytearray)) else unlock_at_raw)
        except Exception:
            return

        now_ts = int(time.time())
        remaining_seconds = unlock_at - now_ts
        if remaining_seconds <= 0:
            # Таймер закончился: очищаем и разрешаем запустить заново.
            async with redis_pool.get_connection() as redis:
                async with redis.pipeline(transaction=True) as pipe:
                    pipe.delete(key)
                    pipe.srem(BOTOHUB_REWARD_USERS_KEY, str(user_id))
                    await pipe.execute()
            unlock_at_raw = None

        # Если сообщение пропало/не сохранено, можно пересоздать сообщение, не меняя unlock_at.
        if unlock_at_raw is not None and message_id_raw is None:
            remaining = _format_remaining(remaining_seconds)
            try:
                msg = await bot.send_message(
                    chat_id=user_id,
                    text=_build_message_text(remaining),
                    reply_markup=_build_reply_kb(remaining),
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                return

            async with redis_pool.get_connection() as redis:
                async with redis.pipeline(transaction=True) as pipe:
                    pipe.hset(key, "message_id", str(msg.message_id))
                    pipe.sadd(BOTOHUB_REWARD_USERS_KEY, str(user_id))
                    await pipe.execute()
        if unlock_at_raw is not None:
            return

    now_ts = int(time.time())
    unlock_at = now_ts + BOTOHUB_REWARD_SECONDS
    remaining = _format_remaining(unlock_at - now_ts)

    try:
        msg = await bot.send_message(
            chat_id=user_id,
            text=_build_message_text(remaining),
            reply_markup=_build_reply_kb(remaining),
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        return

    ttl = BOTOHUB_REWARD_SECONDS + 60 * 60
    async with redis_pool.get_connection() as redis:
        # Атомарно: unlock_at ставим только если его ещё нет, чтобы избежать сброса при гонках.
        created = await redis.hsetnx(key, "unlock_at", str(unlock_at))
        if not created:
            # Таймер уже был создан кем-то параллельно — не создаём второй.
            try:
                await msg.delete()
            except (TelegramForbiddenError, TelegramBadRequest):
                pass
            return

        async with redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, "message_id", str(msg.message_id))
            pipe.expire(key, ttl)
            pipe.sadd(BOTOHUB_REWARD_USERS_KEY, str(user_id))
            await pipe.execute()


async def update_botohub_reward_messages() -> None:
    now_ts = int(time.time())

    async with redis_pool.get_connection() as redis:
        user_ids_raw = await redis.smembers(BOTOHUB_REWARD_USERS_KEY)

    if not user_ids_raw:
        return

    for raw_uid in user_ids_raw:
        uid = raw_uid.decode() if isinstance(raw_uid, (bytes, bytearray)) else str(raw_uid)
        if not uid.isdigit():
            async with redis_pool.get_connection() as redis:
                await redis.srem(BOTOHUB_REWARD_USERS_KEY, uid)
            continue

        user_id = int(uid)
        key = BOTOHUB_REWARD_KEY.format(user_id=user_id)

        async with redis_pool.get_connection() as redis:
            data = await redis.hgetall(key)

        if not data:
            async with redis_pool.get_connection() as redis:
                await redis.srem(BOTOHUB_REWARD_USERS_KEY, uid)
            continue

        message_id_raw = data.get("message_id") if isinstance(data, dict) else None
        if message_id_raw is None:
            message_id_raw = data.get(b"message_id")

        unlock_at_raw = data.get("unlock_at") if isinstance(data, dict) else None
        if unlock_at_raw is None:
            unlock_at_raw = data.get(b"unlock_at")

        if unlock_at_raw is None:
            async with redis_pool.get_connection() as redis:
                await redis.delete(key)
                await redis.srem(BOTOHUB_REWARD_USERS_KEY, uid)
            continue

        try:
            unlock_at = int(unlock_at_raw.decode() if isinstance(unlock_at_raw, (bytes, bytearray)) else unlock_at_raw)
        except Exception:
            async with redis_pool.get_connection() as redis:
                await redis.delete(key)
                await redis.srem(BOTOHUB_REWARD_USERS_KEY, uid)
            continue

        message_id: int | None
        if message_id_raw is None:
            message_id = None
        else:
            try:
                message_id = int(message_id_raw.decode() if isinstance(message_id_raw, (bytes, bytearray)) else message_id_raw)
            except Exception:
                # Не удаляем unlock_at — иначе юзер сможет запустить таймер повторно.
                async with redis_pool.get_connection() as redis:
                    await redis.hdel(key, "message_id")
                message_id = None

        remaining_seconds = unlock_at - now_ts
        if remaining_seconds <= 0:
            try:
                if message_id is not None:
                    await bot.edit_message_text(
                        chat_id=user_id,
                        message_id=message_id,
                        text=(
                            "🎁 Спасибо за подписки!\n\n"
                            f"✅ Прошло 24 часа. Если вы не отписались от каналов — награда +{BOTOHUB_REWARD_STARS} ⭐️ будет начислена."
                        ),
                    )
            except (TelegramForbiddenError, TelegramBadRequest):
                pass
            async with redis_pool.get_connection() as redis:
                await redis.delete(key)
                await redis.srem(BOTOHUB_REWARD_USERS_KEY, uid)
            continue

        if message_id is None:
            continue

        remaining = _format_remaining(remaining_seconds)
        text = _build_message_text(remaining)

        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=text,
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            # Не удаляем unlock_at — иначе юзер сможет запустить таймер повторно.
            # Просто перестаём пытаться редактировать сообщение.
            async with redis_pool.get_connection() as redis:
                await redis.hdel(key, "message_id")
            continue

        await _refresh_reply_keyboard(user_id, remaining)


async def get_botohub_reward_remaining(user_id: int) -> str | None:
    key = BOTOHUB_REWARD_KEY.format(user_id=user_id)
    async with redis_pool.get_connection() as redis:
        unlock_at_raw = await redis.hget(key, "unlock_at")

    if unlock_at_raw is None:
        return None

    try:
        unlock_at = int(unlock_at_raw.decode() if isinstance(unlock_at_raw, (bytes, bytearray)) else unlock_at_raw)
    except Exception:
        return None

    now_ts = int(time.time())
    remaining_seconds = unlock_at - now_ts
    if remaining_seconds <= 0:
        return "00:00"
    return _format_remaining(remaining_seconds)
