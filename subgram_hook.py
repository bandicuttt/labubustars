import asyncio
import config
import time
import hmac
import hashlib
from urllib.parse import quote

from datetime import datetime, timedelta

import pytz

from pathlib import Path

from redis.asyncio import Redis
from contextlib import suppress
from fastapi import FastAPI, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
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

PLANEAPP_DIR = Path(__file__).resolve().parent / "planeapp"


def _plane_day_and_ttl() -> tuple[str, int]:
    tz = pytz.timezone(getattr(config, "TIMEZONE", "UTC"))
    now = datetime.now(tz)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ttl = int((tomorrow - now).total_seconds())
    if ttl <= 0:
        ttl = 60 * 60 * 24
    return now.strftime("%Y%m%d"), ttl


def _plane_sig(*parts: str) -> str:
    msg = "|".join(parts).encode("utf-8")
    secret = str(config.PLANEAPP_SIGN_SECRET).encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


@app.get("/plane")
async def plane_root(request: Request):
    qp = request.query_params
    run = qp.get("run")
    uid = qp.get("uid")
    exp = qp.get("exp")
    seed = qp.get("seed")
    reward = qp.get("reward")
    sig = qp.get("sig")
    ad = qp.get("ad")
    abid = qp.get("abid")

    bot_username = str(getattr(config, "BOT_USERNAME", "")).lstrip("@")
    back_url = f"https://t.me/{bot_username}" if bot_username else ""
    back_q = quote(back_url, safe="") if back_url else ""

    if not (run and uid and exp and seed and reward and sig):
        q = request.url.query
        url = "/plane/" + (f"?{q}" if q else "")
        return RedirectResponse(url=url)

    try:
        uid_i = int(uid)
        exp_i = int(exp)
        seed_i = int(seed)
        reward_f = float(reward)
    except (TypeError, ValueError):
        return RedirectResponse(url="/plane/")

    if exp_i < int(time.time()):
        return RedirectResponse(url="/plane/")

    if seed_i <= 0 or seed_i > 2_147_483_647:
        return RedirectResponse(url="/plane/")

    if reward_f < 0 or reward_f > 1:
        return RedirectResponse(url="/plane/")

    ad_flag = "1" if str(ad).lower() in {"1", "true", "yes"} else "0"

    expected = _plane_sig(run, str(uid_i), str(exp_i), str(seed_i), f"{reward_f:.2f}", ad_flag)
    if not hmac.compare_digest(expected, sig):
        if ad is None:
            expected_legacy = _plane_sig(run, str(uid_i), str(exp_i), str(seed_i), f"{reward_f:.2f}")
            if not hmac.compare_digest(expected_legacy, sig):
                return RedirectResponse(url="/plane/")
        else:
            return RedirectResponse(url="/plane/")

    ttl = max(1, exp_i - int(time.time()))
    redis_key = f"plane:run:{run}"

    async with redis_pool.get_connection() as redis:
        claimed = await redis.set(redis_key, "1", ex=ttl, nx=True)

    if not claimed:
        url = f"/plane/?seed={seed_i}" + (f"&back={back_q}" if back_q else "")
        if ad_flag == "1":
            url += "&ad=1"
            if abid:
                url += f"&abid={quote(str(abid), safe='')}"
        return RedirectResponse(url=url)

    if ad_flag == "1":
        day, day_ttl = _plane_day_and_ttl()
        ad_count_key = f"plane:ad_count:{uid_i}:{day}"
        async with redis_pool.get_connection() as redis:
            new_count = await redis.incr(ad_count_key)
            if new_count == 1:
                await redis.expire(ad_count_key, day_ttl)
        if new_count > 2:
            url = f"/plane/?limit=1" + (f"&back={back_q}" if back_q else "")
            return RedirectResponse(url=url)

    async with db.get_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_user(user_id=uid_i)
        if not user:
            url = f"/plane/?seed={seed_i}" + (f"&back={back_q}" if back_q else "")
            if ad_flag == "1":
                url += "&ad=1"
                if abid:
                    url += f"&abid={quote(str(abid), safe='')}"
            return RedirectResponse(url=url)
        await user_repo.update_user(
            user_id=uid_i,
            important_action=True,
            balance=user.balance + reward_f,
        )

    url = f"/plane/?seed={seed_i}" + (f"&back={back_q}" if back_q else "")
    if ad_flag == "1":
        url += "&ad=1"
        if abid:
            url += f"&abid={quote(str(abid), safe='')}"
    return RedirectResponse(url=url)


app.mount("/plane", StaticFiles(directory=str(PLANEAPP_DIR), html=True), name="plane")


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