import asyncio
import config

from redis.asyncio import Redis
from contextlib import suppress
from fastapi import FastAPI, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from loader import bot
from app.logger import logger

from op.services.op_service import op_client

from app.database import db, redis_pool
from app.database.models import User
from app.templates.texts import unsubscribe_subgram_message
from app.keyboards.inline import subgram_unsubscribed_kb
from app.database.repositories.user_repo import UserRepository


app = FastAPI()

async def proccess_user_reward(user: User, user_repo: UserRepository, url: str, redis_conn: Redis, push: bool = True):
    
    # Отнимаем 0.25 за задание и выставляем subbed=False
    await user_repo.update_user(
        user_id=user.user_id,
        subbed=False,
        balance=user.balance - config.COST_PER_TASK
    )
    clear_cache_result = await op_client.reset_user_cache(user.user_id)

    ref = str(user.ref)

    if ref and ref.isdigit() and not ref == str(user.user_id):

        key = f'reward:{ref}:{user.user_id}'

        if await redis_conn.exists(key):
            ref_user_info = await user_repo.get_user(user_id=int(user.ref))
            
            # Нужно для получения новой награды
            if not clear_cache_result:
                # Если кэш не очистился ставим ттл на некст обновление ОП
                await redis_conn.setex(key, config.OP_TTL, '1')
            else:
                # Если кэш очистился, то удаляем ключ
                await redis_conn.delete(key)

            await user_repo.update_user(
                user_id=int(user.ref),
                balance=ref_user_info.balance - 3
            )

    if push:
        with suppress(TelegramForbiddenError, TelegramBadRequest):
            await bot.send_message(
                chat_id=user.user_id,
                text=unsubscribe_subgram_message,
                reply_markup=subgram_unsubscribed_kb(url)
            )


async def process_flyer(data: dict):
    url = data['data']['link']
    user_id = data['data']['user_id']

    async with db.get_session() as db_session, redis_pool.get_connection() as redis_conn:
        user_repo = UserRepository(db_session)
        user: User | None = await user_repo.get_user(user_id=user_id)
        if not user: return
        await proccess_user_reward(user, user_repo, url, redis_conn)


@app.get('/')
async def index(request: Request,):
    return {"status": "ok"}

@app.post('/webhooks/flyer')
async def flyer_webhook(request: Request,):
    ANSWER = {"processed": [], "status": "accepted"}
    data = await request.json()

    if data['type'] == 'test':
        return ANSWER

    elif data['type'] == 'sub_completed':
        return ANSWER

    elif data['type'] == 'new_status' and data['data']['status'] == 'abort':
        
        asyncio.create_task(
            process_flyer(data,)
        )

        return ANSWER
    return ANSWER

@app.post("/webhooks/subgram")
async def subgram_webhook(request: Request,):
    api_key = request.headers.get("Api-Key")
    if not api_key or api_key != config.SUBGRAM_API_KEY:
        logger.warning(f"Invalid Api-Key from {request.client.host}")
        return {"processed": [], "status": "invalid_api_key"}

    payload = await request.json()
    logger.info(f"Incoming webhook: {payload}")

    events = payload.get("webhooks", [])
    if not isinstance(events, list):
        return {"processed": [], "status": "bad_payload"}

    # Сортируем по webhook_id (если есть)
    events_sorted = sorted(
        events, key=lambda e: e.get("webhook_id", 0)
    )

    asyncio.create_task(
        process_events(events_sorted,)
    )

    # Сразу подтверждаем получение
    return {"processed": [], "status": "accepted"}


async def process_events(events: list):
    results = []

    for event in events:
        user_id = event.get("user_id")
        link = event.get("link")
        status = event.get("status")
        bot_id = event.get("bot_id")
        webhook_id = event.get("webhook_id")

        # Проверяем bot_id
        expected_bot_id = config.BOT_TOKEN.split(":")[0]
        if not bot_id or str(bot_id) != expected_bot_id:
            results.append(
                {
                    "user_id": user_id,
                    "status": status,
                    "result": "ignored_wrong_bot",
                    "bot_id": bot_id,
                    "webhook_id": webhook_id,
                }
            )
            continue

        if not (user_id and link and status):
            continue
        
        async with db.get_session() as db_session, redis_pool.get_connection() as redis_conn:

            user_repo = UserRepository(db_session)
            user: User | None = await user_repo.get_user(user_id=user_id)

            if not user:
                results.append(
                    {"user_id": user_id, "status": status, "result": "no_such_user", "webhook_id": webhook_id}
                )
                continue
            
            redis_key = f"subgram_sub:{user_id}:{link}"
        
            if status in ("subscribed"):
                await redis_conn.set(redis_key, "1", ex=24*60*60*7)
                results.append(
                    {"user_id": user_id, "status": status, "result": "subscribed_saved", "webhook_id": webhook_id}
                )

            elif status == "unsubscribed":
                exists = await redis_conn.exists(redis_key)
                if not exists:
                    results.append(
                        {"user_id": user_id, "status": status, "result": "not_previously_subscribed", "webhook_id": webhook_id}
                    )
                else:
                    await redis_conn.delete(redis_key)
                    await proccess_user_reward(user, user_repo, link, redis_conn)
                    results.append(
                        {"user_id": user_id, "status": status, "result": "unsubscribed_processed", "webhook_id": webhook_id}
                    )

            else:
                results.append(
                    {"user_id": user_id, "status": status, "result": "ignored_status", "webhook_id": webhook_id}
                )

    logger.info(f"Processed webhook events: {results}")