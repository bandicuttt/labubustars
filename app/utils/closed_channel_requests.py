import config

from app.database import redis_pool

CLOSED_CHANNEL_REQUEST_KEY = "closed_channel_request:{chat_id}:{user_id}"


def _normalize_chat_id(chat_id: int | str) -> int | None:
    try:
        return int(chat_id)
    except (TypeError, ValueError):
        return None


async def save_closed_channel_request(chat_id: int | str, user_id: int) -> None:
    normalized_chat_id = _normalize_chat_id(chat_id)
    if normalized_chat_id is None:
        return

    async with redis_pool.get_connection() as conn:
        await conn.setex(
            CLOSED_CHANNEL_REQUEST_KEY.format(chat_id=normalized_chat_id, user_id=user_id),
            config.OP_TTL,
            "1",
        )


async def has_closed_channel_request(chat_id: int | str, user_id: int) -> bool:
    normalized_chat_id = _normalize_chat_id(chat_id)
    if normalized_chat_id is None:
        return False

    async with redis_pool.get_connection() as conn:
        return bool(
            await conn.exists(
                CLOSED_CHANNEL_REQUEST_KEY.format(chat_id=normalized_chat_id, user_id=user_id)
            )
        )
