from aiogram.types import Message
import config
import aiohttp
import asyncio

from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from loader import bot

from app.database import db, redis_pool, repositories
from app.database.models import Advert
from app.utils.utils import get_admins
from app.templates.texts import admin_advert_end_message
from app.logger import logger

ADVERT_REPEAT_PER_ADVERT = getattr(config, "ADVERT_REPEAT_PER_ADVERT", 1)

# интервал между одинаковыми показами одного и того же advert
ADVERT_REPEAT_INTERVAL_SECONDS = getattr(config, "ADVERT_REPEAT_INTERVAL_SECONDS", 30)

# интервал между разными объявлениями (после того как показали advert N раз)
ADVERT_BETWEEN_ADVERTS_INTERVAL_SECONDS = getattr(config, "ADVERT_BETWEEN_ADVERTS_INTERVAL_SECONDS", 30)

# ретраи одного конкретного показа (если не удалось отправить)
ADVERT_SEND_RETRY_INTERVAL_SECONDS = getattr(config, "ADVERT_SEND_RETRY_INTERVAL_SECONDS", 30)
ADVERT_SEND_MAX_RETRIES = getattr(config, "ADVERT_SEND_MAX_RETRIES", 3)


class AdvertService:

    def __init__(self):
        self.gramads_token = config.GRAMADS_API_KEY
        self._spam_locks: dict[int, asyncio.Lock] = {}

    async def send_advert(self, user_id: int, advert: Advert | int, write_history: bool = True) -> bool:
        if isinstance(advert, int):
            async with db.get_session() as session:
                advert_repo = repositories.AdvertRepository(session)
                advert = await advert_repo.get_advert_by_id(advert)
            if not advert:
                print(f"no advert found id{advert}")
                return False
        try:
            print(f"still sending adv to {user_id}")
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=advert.from_chat_id,
                message_id=advert.message_id,
                reply_markup=advert.reply_markup
            )
            if write_history:
                await self.write_advert_history(user_id=user_id, advert=advert)
            return True
        except Exception as e:
            logger.error(f"Error sending advert {advert.id} to user {user_id}: {e}", exc_info=True)
            return False

    async def send_admin_alert(self, advert: Advert):
        for admin in get_admins():
            with suppress(TelegramForbiddenError, TelegramBadRequest):
                await bot.send_message(
                    chat_id=admin,
                    text=admin_advert_end_message.format(
                        title=advert.title,
                        views=advert.views,
                        viewed=advert.viewed
                    )
                )

    async def write_advert_history(self, user_id: int, advert: Advert):
        async with db.get_session() as session:
            try:
                advert_repo = repositories.AdvertRepository(session)
                history_repo = repositories.AdvertHistoryRepository(session)

                await advert_repo.mark_advert_shown(user_id, advert.id)
                await history_repo.create_advert_history(ad_id=advert.id, user_id=user_id)
                updated_advert: Advert = await advert_repo.update_advert_views(advert.id)

                if updated_advert and updated_advert.viewed >= updated_advert.views:
                    await advert_repo.update_advert(advert.id, status=False)
                    await advert_repo.invalidate_adverts_cache()  # Сбрасываем кэш
                    await self.send_admin_alert(updated_advert)

            except Exception as e:
                logger.error(f"Error writing advert history: {e}", exc_info=True)

    async def fetch_gramads(self, user_id: int) -> bool:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                        'https://api.gramads.net/ad/SendPost',
                        headers={
                            'Authorization': f'Bearer {self.gramads_token}',
                            'Content-Type': 'application/json',
                        },
                        json={'SendToChatId': user_id},
                ) as response:
                    if response.status == 200:
                        logger.info(f"Gramads ad sent to user {user_id}")
                        return True
                    else:
                        logger.warning(f"Gramads API error: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Gramads request failed for user {user_id}: {e}", exc_info=True)
            return False

    async def get_manual_advert(self, user_id: int, only_start: bool = False, ignore_history: bool = False) \
            -> Advert | None:
        async with db.get_session() as session:
            advert_repo = repositories.AdvertRepository(session)
            if ignore_history:
                return await advert_repo.get_all_adverts(count=False)
            return await advert_repo.get_advert_for_user(user_id, only_start)

    async def send(self, user_id: int, message: Message):
        try: 
            text = getattr(message, 'text', '')
            only_start = False
            if text:
                text = text.strip()
                only_start = text.startswith("/start")
            advert = await self.get_manual_advert(user_id, only_start)

            if advert and await self.send_advert(user_id, advert):
                await asyncio.sleep(1.5)
                return True

            # Запускаем Gramads асинхронно без ожидания
            if not only_start:
                asyncio.create_task(self.fetch_gramads(user_id))

            return False  # Возвращаем False так как Gramads запущен в фоне

        except Exception as e:
            print(str(e))
            return False

    def _get_spam_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._spam_locks:
            self._spam_locks[user_id] = asyncio.Lock()
        return self._spam_locks[user_id]

    async def _send_advert_with_retries(self, user_id: int, advert: Advert, *, write_history: bool) -> bool:
        """
        ОДНА попытка показа (одно сообщение) с ретраями.
        """
        for attempt in range(1, ADVERT_SEND_MAX_RETRIES + 1):
            ok = await self.send_advert(user_id, advert, write_history=write_history)
            if ok:
                return True
            if attempt < ADVERT_SEND_MAX_RETRIES:
                await asyncio.sleep(ADVERT_SEND_RETRY_INTERVAL_SECONDS)
        return False

    async def start_advert_spam(self, user_id: int):
        """
        Шлёт список доступных объявлений (ignore_history=True),
        каждое объявление — ADVERT_REPEAT_PER_ADVERT раз,
        с паузой ADVERT_REPEAT_INTERVAL_SECONDS между одинаковыми показами,
        и паузой ADVERT_BETWEEN_ADVERTS_INTERVAL_SECONDS между разными объявлениями.
        """
        lock = self._get_spam_lock(user_id)
        if lock.locked():
            logger.info(f"Advert spam already running for user {user_id}")
            return

        try:
            async with lock:
                adverts = await self.get_manual_advert(user_id, ignore_history=True)
                if not adverts:
                    return

                total = len(adverts)
                for idx, advert in enumerate(adverts, start=1):
                    # Каждый advert показываем N раз
                    for show_num in range(1, ADVERT_REPEAT_PER_ADVERT + 1):
                        sent_ok = await self._send_advert_with_retries(
                            user_id,
                            advert,
                            write_history=False
                        )

                        if sent_ok:
                            logger.info(
                                f"Advert {advert.id} sent to user {user_id} "
                                f"(show {show_num}/{ADVERT_REPEAT_PER_ADVERT}, advert {idx}/{total})"
                            )
                        else:
                            logger.warning(
                                f"Failed to send advert {advert.id} to user {user_id} "
                                f"on show {show_num}/{ADVERT_REPEAT_PER_ADVERT} "
                                f"after {ADVERT_SEND_MAX_RETRIES} retries"
                            )
                            # если принципиально: при фейле прекращаем всю рассылку
                            return

                        # Пауза между одинаковыми показами (если это не последний показ)
                        if show_num < ADVERT_REPEAT_PER_ADVERT:
                            await asyncio.sleep(ADVERT_REPEAT_INTERVAL_SECONDS)

                    # Пауза между разными объявлениями (если это не последнее объявление)
                    if idx < total:
                        await asyncio.sleep(ADVERT_BETWEEN_ADVERTS_INTERVAL_SECONDS)

        except asyncio.CancelledError:
            logger.info(f"Advert spam task cancelled for user {user_id}")
            raise
        except Exception as e:
            logger.error(f"Error in start_advert_spam for user {user_id}: {e}", exc_info=True)


adverts_client = AdvertService()

