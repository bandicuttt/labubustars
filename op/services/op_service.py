import time
from typing import Callable, Optional, Any

import config
import asyncio
import aiohttp
import json

from pydantic import BaseModel
from enum import Enum
from redis.exceptions import WatchError

from flyerapi import APIError

from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.logger import logger
from app.database import flyer, db, redis_pool
from app.database.models import Subscribe
from app.database.repositories import SubscribeRepository, SubscriptionHistoryRepository, UserRepository
from app.utils.utils import check_for_bot, check_subscribe_channel

REDIS_CACHE_KEY = 'op_cache:{}'
FLYER_TASKS_CACHE_KEY = 'flyer_op_cache:{}'
BOTOHUB_COOLDOWN_KEY = 'botohub:cooldown:{}'


class ActionEnum(str, Enum):
    bot = "bot"
    channel = "channel"
    boost = "boost"
    visit = "visit"


class SubscribeModel(BaseModel):
    url: str
    is_manual: bool
    action: ActionEnum


class OPService:
    def __init__(self, ):
        self.flyer = flyer
        self.subgram_api_key = config.SUBGRAM_API_KEY
        self.max_op = config.MAX_OP
        self.botohub_api_url = getattr(config, "BOTOHUB_API_URL", "https://botohub.me/get-tasks")
        self.botohub_api_token = getattr(config, "BOTOHUB_API_TOKEN", None)
        self.botohub_cooldown = 0  # getattr(config, "BOTOHUB_COOLDOWN", 0)
        self.action_map = {
            # Боты
            "bot": ActionEnum.bot,
            "start_bot": ActionEnum.bot,
            "start bot": ActionEnum.bot,

            # Каналы
            "channel": ActionEnum.channel,
            "subscribe": ActionEnum.channel,
            "subscribe channel": ActionEnum.channel,

            # Прочее дермьо
            "perform action": ActionEnum.visit,
            "perform_action": ActionEnum.visit,
            "follow link": ActionEnum.visit,
            "give boost": ActionEnum.boost,
            "resource": ActionEnum.visit
        }
        # self.button_data = {
        #     ActionEnum.channel: '🔔 Вступить',
        #     ActionEnum.bot: '🤖 Запустить бота',
        #     ActionEnum.visit: '☑️ Выполнить',
        #     ActionEnum.boost: '🗣 Голосовать (3 раза)'
        # }
        self.button_data = "Подписаться ☑️"

    async def reset_user_cache(self, user_id: int) -> bool:
        try:
            async with redis_pool.get_connection() as conn:
                if conn is None:
                    logger.error(f"Redis connection is None for user {user_id}")
                    return False

                key = REDIS_CACHE_KEY.format(user_id)
                result = await conn.delete(key)

                if result == 1:
                    logger.info(f"Cache reset for user {user_id}")
                    return True
                else:
                    logger.warning(f"No cache found to reset for user {user_id}")
                    return False

        except Exception as e:
            logger.error(f"Error resetting cache for user {user_id}: {e}", exc_info=True)
            return False

    async def build_reply_markup(self, sponsors: list[SubscribeModel], done_cb: str = None) -> InlineKeyboardMarkup:
        buttons: list[InlineKeyboardButton] = []

        for sponsor in sponsors:
            buttons.append(InlineKeyboardButton(text=self.button_data, url=sponsor.url))

        keyboard_rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]

        keyboard_rows.append([
            InlineKeyboardButton(text=f"✅ Готово ({len(sponsors)})", callback_data=done_cb or "op_done")
        ])
        return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    async def save_sponsors_cache(self, user_id: int, cache_data: dict, completed: bool = False):
        """Сохраняет кэш спонсоров в Redis с флагом завершения (атомарно)"""
        try:
            async with redis_pool.get_connection() as conn:
                if conn is None:
                    logger.error(f"Redis connection is None for user {user_id}")
                    return

                key = REDIS_CACHE_KEY.format(user_id)

                async with conn.pipeline(transaction=True) as pipe:
                    while True:
                        try:
                            await pipe.watch(key)

                            existing_cache_json = await pipe.get(key)
                            existing_cache = {}
                            if existing_cache_json is not None:
                                try:
                                    existing_cache = json.loads(existing_cache_json)
                                    if 'completed' in existing_cache and not completed:
                                        completed = existing_cache['completed']
                                except json.JSONDecodeError:
                                    existing_cache = {}

                            for key_name in cache_data:
                                existing_cache[key_name] = cache_data[key_name]

                            existing_cache['completed'] = completed

                            pipe.multi()  # ← УБРАТЬ await!
                            pipe.set(
                                key,
                                json.dumps(existing_cache),
                                ex=config.OP_TTL
                            )
                            await pipe.execute()  # ← ТОЛЬКО ЗДЕСЬ await!
                            break

                        except WatchError:
                            continue

        except Exception as e:
            logger.error(f"Error saving cache for user {user_id}: {e}", exc_info=True)

    def get_action(self, type_: str) -> ActionEnum:
        type_lower = type_.lower()
        try:
            return self.action_map[type_lower]
        except KeyError:
            raise ValueError(f"Unknown sponsor type: {type_}")

    async def get_flyer_sponsors(
            self,
            max_op: int,
            user_id: int,
            language_code: str,
            cached_sponsors: dict | None
    ) -> list[SubscribeModel]:
        _incomplete_statuses = ('incomplete', 'abort')

        # ускоряем функу
        if max_op <= 0:
            if not cached_sponsors or 'flyer_data_cache' not in cached_sponsors:
                cache_data = {
                    'flyer_data_cache': {
                        'sponsors_count': 0,
                        'sponsors': []
                    }
                }
                await self.save_sponsors_cache(user_id, cache_data)
                return []
            return []

        try:
            # Если нет кэша, делаем обычный запрос
            if not cached_sponsors or 'flyer_data_cache' not in cached_sponsors:
                tasks = await flyer.get_tasks(user_id=user_id, language_code=language_code, limit=max_op)
                print(f"FLYER_RESP: {str(tasks)}")

                if not tasks:
                    cache_data = {
                        'flyer_data_cache': {
                            'sponsors_count': 0,
                            'sponsors': []
                        }
                    }
                    await self.save_sponsors_cache(user_id, cache_data)
                    return []

                # Фильтруем только incomplete и без iOS бана ДЛЯ ПОКАЗА
                tasks_incomplete = sorted(
                    [
                        task for task in tasks
                        if task['status'] in _incomplete_statuses and \
                           not task['is_ios_ban'] and
                           all('https://api.flyerpartners.com/' not in link for link in task.get('links', []))
                    ],
                    key=lambda x: x['price'],
                    reverse=True
                )

                tasks_to_show = tasks_incomplete[:min(len(tasks_incomplete), max_op)]

                # Сохраняем в кэш только ПОКАЗАННЫЕ задачи (с signature!)
                cache_data = {
                    'flyer_data_cache': {
                        'sponsors_count': len(tasks_to_show),
                        'sponsors': tasks_to_show
                    }
                }
                # await self.save_sponsors_cache(user_id, cache_data)
                subscribes: list[SubscribeModel] = []
                for task in tasks_to_show:
                    task_status = await flyer.check_task(user_id=user_id, signature=task['signature'])

                    # Обрабатываем разные форматы ответа
                    status_result = None
                    if isinstance(task_status, dict):
                        status_result = task_status.get('result')
                    elif isinstance(task_status, str):
                        status_result = task_status

                    # Добавляем только если задача все еще incomplete
                    if status_result in _incomplete_statuses:
                        subscribes.append(
                            SubscribeModel(
                                url=task['links'][0],
                                is_manual=False,
                                action=self.get_action(task['task'])
                            )
                        )
                print(f"INCOMPLETE_FLYER FOR {str(user_id)}: {str(subscribes)}")
                return subscribes

            # Если есть кэш, работаем с кэшированными задачами
            if 'flyer_data_cache' not in cached_sponsors:
                cache_data = {
                    'flyer_data_cache': {
                        'sponsors_count': 0,
                        'sponsors': []
                    }
                }
                await self.save_sponsors_cache(user_id, cache_data)

            cache_data = cached_sponsors['flyer_data_cache']
            cached_tasks = cache_data.get('sponsors', [])

            subscribes: list[SubscribeModel] = []

            # Проверяем статус каждой кэшированной задачи
            for cached_task in cached_tasks:
                # Пропускаем iOS бан
                if cached_task.get('is_ios_ban', False):
                    continue
                if 'https://api.flyerpartners.com' in cached_task.get('link', ''):
                    continue

                # Проверяем актуальный статус задачи
                try:
                    task_status = await flyer.check_task(user_id=user_id, signature=cached_task['signature'])

                    # Обрабатываем разные форматы ответа
                    status_result = None
                    if isinstance(task_status, dict):
                        status_result = task_status.get('result')
                    elif isinstance(task_status, str):
                        status_result = task_status

                    # Добавляем только если задача все еще incomplete
                    if status_result in _incomplete_statuses:
                        subscribes.append(
                            SubscribeModel(
                                url=cached_task['link'],
                                is_manual=False,
                                action=self.get_action(cached_task['task'])
                            )
                        )

                except Exception as err:
                    logger.error(f"Error checking Flyer task {cached_task['signature']}: {err}", exc_info=True)
                    continue

            return subscribes

        except APIError:
            return []
        except Exception as err:
            logger.error(f"Error in get_flyer_sponsors: {err}", exc_info=True)
            return []

    async def fetch_subgram(self, max_op: int, user_id: int):
        headers = {
            'Content-Type': 'application/json',
            'Auth': self.subgram_api_key,
            'Accept': 'application/json',
        }
        data = {
            'UserId': user_id,
            'ChatId': user_id,
            'MaxOp': max_op
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    'https://api.subgram.ru/request-op/',
                    headers=headers,
                    json=data
            ) as response:

                if not response.ok:
                    return []

                response_json = await response.json()
                print(f"SUBGRAM_RESP: {str(response_json)}")

                additioanl_info = response_json.get('additional')

                if not additioanl_info:
                    return []

                sponsors = additioanl_info.get('sponsors')

                if not sponsors:
                    return []
                return sponsors

    async def get_subgram_sponsors(
            self,
            max_op: int,
            user_id: int,
            language_code: str,
            cached_sponsors: dict | None
    ) -> list[SubscribeModel]:
        try:
            # Ускоряем функу
            if max_op <= 0:
                if not cached_sponsors or 'subgram_data_cache' not in cached_sponsors:
                    cache_data = {
                        'subgram_data_cache': {
                            'sponsors_count': 0,
                            'sponsors': []
                        }
                    }
                    await self.save_sponsors_cache(user_id, cache_data)
                    return []
                return []

            subscribes: list[SubscribeModel] = []

            # Если нет кэша, делаем обычный запрос
            if not cached_sponsors or 'subgram_data_cache' not in cached_sponsors:
                subgram_data = await self.fetch_subgram(max_op, user_id)

                if not subgram_data:
                    cache_data = {
                        'subgram_data_cache': {
                            'sponsors_count': 0,
                            'sponsors': []
                        }
                    }
                    await self.save_sponsors_cache(user_id, cache_data)
                    return []

                # Фильтруем только неподписанных
                sponsors = [sub for sub in subgram_data if sub['status'] == 'unsubscribed']
                sponsors_to_show = sponsors[:min(len(sponsors), max_op)]

                # Сохраняем в кэш только ПОКАЗАННЫХ спонсоров
                cache_data = {
                    'subgram_data_cache': {
                        'sponsors_count': len(sponsors_to_show),
                        'sponsors': sponsors_to_show  # ← только показанные!
                    }
                }
                await self.save_sponsors_cache(user_id, cache_data)

                for sponsor in sponsors_to_show:
                    subscribes.append(
                        SubscribeModel(
                            url=sponsor['link'],
                            is_manual=False,
                            action=self.get_action(sponsor['type'])
                        )
                    )
                return subscribes

            # Если есть кэш, работаем только с кэшированными спонсорами
            if 'subgram_data_cache' not in cached_sponsors:
                cache_data = {
                    'subgram_data_cache': {
                        'sponsors_count': 0,
                        'sponsors': []
                    }
                }
                await self.save_sponsors_cache(user_id, cache_data)
                return []

            cache_data = cached_sponsors['subgram_data_cache']
            cached_sponsors_list = cache_data.get('sponsors', [])

            # Получаем актуальные данные для проверки статуса
            subgram_data = await self.fetch_subgram(len(cached_sponsors_list), user_id)

            # Создаем словарь для быстрого поиска актуальных статусов по ссылке
            actual_statuses = {sponsor['link']: sponsor['status'] for sponsor in subgram_data}

            # Проверяем только тех спонсоров, которые были в кэше
            for cached_sponsor in cached_sponsors_list:
                link = cached_sponsor['link']

                # Если спонсор все еще не подписан
                if (link in actual_statuses and
                        actual_statuses[link] == 'unsubscribed'):
                    subscribes.append(
                        SubscribeModel(
                            url=cached_sponsor['link'],
                            is_manual=False,
                            action=self.get_action(cached_sponsor['type'])
                        )
                    )

            return subscribes

        except Exception as err:
            logger.error(f"Error in get_subgram_sponsors: {err}", exc_info=True)
            return []

    async def tgrass_get_offers(
        self,
        tg_user_id: int,
        is_premium: bool,
        *,
        lang: str = "ru",
        tg_login: Optional[str] = None,
        gender: Optional[str] = None,
        exclude_channels: Optional[list[str]] = None,
        offers_limit: Optional[int] = None,
        session: Optional[aiohttp.ClientSession] = None,
        timeout_sec: int = 20,
    ) -> dict[str, Any]:
        url = "https://tgrass.space/offers"
        headers = {
            "Content-Type": "application/json",
            "Auth": config.TGRASS_API_KEY,
        }

        payload: dict[str, Any] = {
            "tg_user_id": tg_user_id,
            "is_premium": is_premium,
            "lang": lang,
        }
        if tg_login is not None:
            payload["tg_login"] = tg_login
        if gender is not None:
            payload["gender"] = gender
        if exclude_channels is not None:
            payload["exclude_channels"] = exclude_channels
        if offers_limit is not None:
            payload["offers_limit"] = offers_limit

        close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.post(url, json=payload, headers=headers, timeout=timeout_sec) as resp:
                print(f"TGRASS_RESP: {str(await resp.json())}")
                return await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"Error getting offers for user {tg_user_id}: {e}", exc_info=True)

    async def tgrass_reset_offers(
        self,
        tg_user_id: int,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        timeout_sec: int = 20,
    ) -> dict[str, Any]:
        url = "https://tgrass.space/reset_offers"
        headers = {
            "Content-Type": "application/json",
            "Auth": config.TGRASS_API_KEY,
        }
        payload = {"tg_user_id": tg_user_id}

        close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.post(url, json=payload, headers=headers, timeout=timeout_sec) as resp:
                return await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"Error resetting offers for user {tg_user_id}: {e}", exc_info=True)

    async def get_tgrass_sponsors(
        self,
        max_op: int,
        user_id: int,
        message: Message | None,
        language_code: str,
    ) -> list[SubscribeModel]:
        if max_op <= 0:
            return []

        is_premium = bool(message and getattr(message.from_user, "is_premium", False))
        tg_login = None
        if message and message.from_user:
            tg_login = message.from_user.username

        data = await self.tgrass_get_offers(
            tg_user_id=user_id,
            is_premium=is_premium,
            lang=language_code,
            tg_login=tg_login,
            offers_limit=max_op,
        )
        offers_raw = []
        if isinstance(data, dict):
            offers_raw = (
                data.get("offers")
                or data.get("sponsors")
                or data.get("tasks")
                or data.get("data")
                or []
            )
        elif isinstance(data, list):
            offers_raw = data

        sponsors: list[SubscribeModel] = []
        for offer in offers_raw:
            if isinstance(offer, str):
                url = offer
                offer_type = "channel"
            elif isinstance(offer, dict):
                if offer.get("subscribed"):
                    continue
                url = offer.get("link") or offer.get("url")
                offer_type = offer.get("type") or offer.get("task") or "channel"
            else:
                continue
            if not url:
                continue
            try:
                action = self.get_action(str(offer_type))
            except ValueError:
                action = ActionEnum.channel
            sponsors.append(
                SubscribeModel(
                    url=url,
                    is_manual=False,
                    action=action,
                )
            )
        print(f"TGRASS_SPONSORS FOR {str(user_id)}: {str(sponsors)}")
        return sponsors

    async def check_tgrass(
        self,
        user_id: int,
        message: Message,
        language_code: str = "ru",
        max_op: int | None = None,
        done_cb: str | None = None,
    ) -> InlineKeyboardMarkup | None:
        sponsors = await self.get_tgrass_sponsors(
            max_op=max_op or self.max_op,
            user_id=user_id,
            message=message,
            language_code=language_code,
        )
        if sponsors:
            return await self.build_reply_markup(sponsors, done_cb)
        async with db.get_session() as session:
            user_repo = UserRepository(session)
            await user_repo.set_user_subbed(user_id, True, True)
        return None

    async def write_sub_history(self, sponsors: list[Subscribe], user_id: int, session: AsyncSession):
        subscribe_history_repo = SubscriptionHistoryRepository(session)
        for sub in sponsors:
            exists = await subscribe_history_repo.check_subscription_exists(user_id, sub.id)
            if not exists:
                await subscribe_history_repo.create_subscription_history(
                    user_id=user_id,
                    sub_id=sub.id
                )
            await subscribe_history_repo.update_subscribers_count(sub.id)

            if sub.subscribed_count >= sub.subscribe_count:
                sub.status = False

    async def check_manual_sponsors(self, sponsors: list[Subscribe], user_id: int, session: AsyncSession,
                                    write_history: bool = False) -> list[Subscribe]:
        wo_check = [i for i in sponsors if not i.access]
        to_check = [i for i in sponsors if i.access]
        print("WO_CHECK: " + str([s.url for s in wo_check]))
        print("TO_CHECK: " + str([s.url for s in to_check]))

        tasks = [
            check_for_bot(user_id, sub) if sub.is_bot
            else check_subscribe_channel(user_id, sub)
            for sub in to_check
        ]
        results = await asyncio.gather(*tasks)
        print("RESULTS: " + str([("NOT OK" if res1 else "OK", res2.url) for res1, res2 in results]))
        not_subbed = [sub[1] for sub in results if sub[0] is not None]
        subbed = [sub[1] for sub in results if sub[0] is None]
        print("NOT_SUBBED: " + str([s.url for s in not_subbed]))
        if write_history and (subbed or wo_check):
            await self.write_sub_history(
                sponsors=subbed + wo_check,
                user_id=user_id,
                session=session
            )

        if not not_subbed:
            return []

        return not_subbed + wo_check if not write_history else not_subbed

    async def get_manual_sponsors(self, max_op: int | None, user_id: int, language_code: str, cached_sponsors: dict | None) -> \
            list[SubscribeModel]:
        # Ускоряем функу
        if max_op is not None and max_op <= 0:
            if not cached_sponsors or 'manual_data_cache' not in cached_sponsors:
                cache_data = {
                    'manual_data_cache': {
                        'sponsors_count': 0,
                        'sponsor_urls': []
                    }
                }
                await self.save_sponsors_cache(user_id, cache_data)
                return []
            return []

        async with db.get_session() as session:
            subscribe_repo = SubscribeRepository(session)
            unlimited = max_op is None

            # Если нет кэша - получаем новых спонсоров
            if not cached_sponsors or 'manual_data_cache' not in cached_sponsors:
                all_sponsors: list[Subscribe] = []
                batch_size = max_op * 3
                batch_size = (max_op or self.max_op) * 3

                # Получаем спонсоров батчами до заполнения max_op
                page = 0
                while True:
                    if not unlimited and len(all_sponsors) >= max_op:
                        break

                    batch_sponsors: list[Subscribe] = await subscribe_repo.get_active_sponsors_batch(
                        user_id=user_id,
                        limit=batch_size,
                        page=page
                    )

                    if not batch_sponsors:
                        break

                    # Проверяем подписки для этой пачки
                    checked_batch: list[Subscribe] = await self.check_manual_sponsors(
                        sponsors=batch_sponsors,
                        user_id=user_id,
                        session=session,
                        write_history=False
                    )

                    # Добавляем только неподписанных
                    all_sponsors.extend(checked_batch)

                    # Если на этой странице все подписаны, продолжаем
                    if not checked_batch:
                        page += 1
                        continue
                    page += 1

                # Ограничиваем количество
                final_sponsors = all_sponsors if unlimited else all_sponsors[:max_op]

                # Фильтруем: должны быть хотя бы 1 спонсор с access
                sponsors_with_access = [sponsor for sponsor in final_sponsors if sponsor.access]
                print("ALL_MANUAL:" + str([s.url for s in sponsors_with_access]))
                if not sponsors_with_access:
                    print("NO ACCESS")
                    cache_data = {
                        'manual_data_cache': {
                            'sponsor_urls': []
                        }
                    }
                    await self.save_sponsors_cache(user_id, cache_data)
                    return []

                # Сохраняем в кэш
                cache_data = {
                    'manual_data_cache': {
                        'sponsor_urls': [sponsor.url for sponsor in final_sponsors]
                    }
                }
                await self.save_sponsors_cache(user_id, cache_data)

                # Формируем результат
                subscribes: list[SubscribeModel] = []
                for sponsor in final_sponsors:
                    subscribes.append(
                        SubscribeModel(
                            url=sponsor.url,
                            is_manual=True,
                            action=ActionEnum.bot if sponsor.is_bot else ActionEnum.channel
                        )
                    )
                return subscribes

            # Если есть кэш - работаем с кэшированными спонсорами
            cache_data = cached_sponsors['manual_data_cache']
            cached_urls = cache_data['sponsor_urls']

            # Получаем спонсоров по URL из кэша
            active_sponsors: list[Subscribe] = await subscribe_repo.get_by_urls(cached_urls)

            if not active_sponsors:
                cache_data = {
                    'manual_data_cache': {
                        'sponsor_urls': []
                    }
                }
                await self.save_sponsors_cache(user_id, cache_data)
                return []

            # Разделяем спонсоров с access и без
            sponsors_with_access = [sponsor for sponsor in active_sponsors if sponsor.access]
            sponsors_without_access = [sponsor for sponsor in active_sponsors if not sponsor.access]

            # Проверяем только спонсоров с access
            checked_sponsors: list[Subscribe] = await self.check_manual_sponsors(
                sponsors=sponsors_with_access,  # Проверяем только тех, у кого есть access
                user_id=user_id,
                session=session,
                write_history=True  # Пишем историю для подписавшихся
            )

            # Добавляем спонсоров без access (они считаются "подписанными" при повторном запросе)
            # и записываем их в историю
            if sponsors_without_access:
                await self.write_sub_history(
                    sponsors=sponsors_without_access,
                    user_id=user_id,
                    session=session
                )

            # Формируем результат: только те, кто еще не подписался + спонсоры без access не возвращаем
            subscribes: list[SubscribeModel] = []
            for sponsor in checked_sponsors:
                subscribes.append(
                    SubscribeModel(
                        url=sponsor.url,
                        is_manual=True,
                        action=ActionEnum.bot if sponsor.is_bot else ActionEnum.channel
                    )
                )
            remaining_sponsors = checked_sponsors  # ← только те, кто еще не подписан
            await self.save_sponsors_cache(user_id, {
                'manual_data_cache': {
                    'sponsor_urls': [sponsor.url for sponsor in remaining_sponsors]
                }
            })
            return subscribes

    # async def get_sponsors(
    #         self,
    #         user_id: int,
    #         message: Message,
    #         language_code: str = "ru",
    #         no_flyer: bool = False,
    #         no_subgram: bool = False,
    #         no_manual: bool = False,
    # ) -> list[SubscribeModel]:
    #     try:
    #         sponsors: list[SubscribeModel] = []
    #         remaining = self.max_op
    #
    #         if message:
    #             is_premium: bool | None = message.from_user.is_premium
    #         else:
    #             is_premium = False
    #
    #         # Получаем кэш
    #         cache = None
    #         async with redis_pool.get_connection() as conn:
    #             cache_json = await conn.get(REDIS_CACHE_KEY.format(user_id))
    #             if cache_json:
    #                 cache = json.loads(cache_json)
    #                 if cache.get('completed', False):
    #                     return []
    #
    #         # Если кэша нет - просто получаем спонсоров
    #         if not cache:
    #
    #             # Определяем порядок источников в зависимости от premium статуса
    #             if is_premium:
    #                 # Premium: Флаер -> Сабграм -> Ручные ОП
    #                 flyer_sponsors = await self.get_flyer_sponsors(remaining, user_id, language_code, None)
    #                 sponsors.extend(flyer_sponsors)
    #                 remaining -= len(flyer_sponsors)
    #
    #                 subgram_sponsors = await self.get_subgram_sponsors(remaining, user_id, language_code, None)
    #                 sponsors.extend(subgram_sponsors)
    #                 remaining -= len(subgram_sponsors)
    #
    #                 manual_sponsors = await self.get_manual_sponsors(remaining, user_id, language_code, None)
    #                 sponsors.extend(manual_sponsors)
    #             else:
    #                 # Non-premium: Сабграм -> Флаер -> Ручные ОП
    #                 manual_sponsors = await self.get_manual_sponsors(remaining, user_id, language_code, None)
    #                 sponsors.extend(manual_sponsors)
    #                 remaining -= len(manual_sponsors)
    #
    #                 subgram_sponsors = await self.get_subgram_sponsors(remaining, user_id, language_code, None)
    #                 sponsors.extend(subgram_sponsors)
    #                 remaining -= len(subgram_sponsors)
    #
    #                 flyer_sponsors = await self.get_flyer_sponsors(remaining, user_id, language_code, None)
    #                 sponsors.extend(flyer_sponsors)
    #             return sponsors
    #
    #         # Если кэш есть - работаем только с кэшированными данными
    #         # Определяем порядок источников в зависимости от premium статуса
    #         if is_premium:
    #             # Premium: Флаер -> Сабграм -> Ручные ОП
    #             sources = [
    #                 lambda: self.get_flyer_sponsors(remaining, user_id, language_code, cache),
    #                 lambda: self.get_subgram_sponsors(remaining, user_id, language_code, cache),
    #                 lambda: self.get_manual_sponsors(remaining, user_id, language_code, cache),
    #             ]
    #         else:
    #             # Non-premium: Сабграм -> Флаер -> Ручные ОП
    #             sources = [
    #                 lambda: self.get_manual_sponsors(remaining, user_id, language_code, cache),
    #                 lambda: self.get_subgram_sponsors(remaining, user_id, language_code, cache),
    #                 lambda: self.get_flyer_sponsors(remaining, user_id, language_code, cache),
    #             ]
    #
    #         for get_source_sponsors in sources:
    #             new_sponsors = await get_source_sponsors()
    #             sponsors.extend(new_sponsors)
    #             remaining -= len(new_sponsors)
    #
    #         # Если спонсоров нет - устанавливаем флаг completed
    #         if not sponsors and cache:
    #             await self.save_sponsors_cache(user_id, cache, completed=True)
    #
    #         return sponsors
    #
    #     except Exception as e:
    #         logger.error(f"Error getting sponsors for user {user_id}: {e}", exc_info=True)
    #         return []

    async def get_sponsors(
            self,
            user_id: int,
            message: Message,
            language_code: str = "ru",
            no_flyer: bool = False,
            no_subgram: bool = False,
            no_manual: bool = False,
            max_op: int | None = None,
            manual_unlimited: bool = False,
    ) -> list[SubscribeModel]:
        try:
            sponsors: list[SubscribeModel] = []
            remaining = max_op or self.max_op

            # Если все источники отключены флагами — сразу выходим, кэш не трогаем
            if no_flyer and no_subgram and no_manual:
                return []

            # Определяем премиум-статус
            is_premium: bool = bool(message and getattr(message.from_user, "is_premium", False))

            # Получаем кэш
            cache = None

            # async with redis_pool.get_connection() as conn:
            #     cache_json = await conn.get(REDIS_CACHE_KEY.format(user_id))
            #     if cache_json:
            #         cache = json.loads(cache_json)
            #         requesting_all = not (no_flyer or no_subgram or no_manual)
            #         if cache.get("completed", False) and requesting_all:
            #             return []

            # Вспомогательная функция для построения пайплайна с учётом флагов
            def build_sources(use_cache: bool) -> list[Callable]:
                lst: list[Callable] = []

                def add(skip: bool, fn):
                    if not skip:
                        lst.append(fn)

                # порядок зависит от премиума, а наличие кэша — от use_cache
                src_cache = cache if use_cache else None
                manual_limit = None if manual_unlimited else remaining
                if is_premium:
                    # Premium: Флаер -> Сабграм -> Ручные ОП
                    add(no_flyer, lambda: self.get_flyer_sponsors(remaining, user_id, language_code, src_cache))
                    add(no_subgram, lambda: self.get_subgram_sponsors(remaining, user_id, language_code, src_cache))
                    add(no_manual, lambda: self.get_manual_sponsors(manual_limit, user_id, language_code, src_cache))
                else:
                    # Non-premium: Ручные ОП -> Сабграм -> Флаер
                    add(no_manual, lambda: self.get_manual_sponsors(manual_limit, user_id, language_code, src_cache))
                    add(no_subgram, lambda: self.get_subgram_sponsors(remaining, user_id, language_code, src_cache))
                    add(no_flyer, lambda: self.get_flyer_sponsors(remaining, user_id, language_code, src_cache))
                return lst

            # Если кэша нет — работаем со «свежими» источниками
            if not cache:
                for fetch in build_sources(use_cache=False):
                    if remaining <= 0:
                        break
                    new_sponsors = await fetch()
                    if not new_sponsors:
                        continue
                    sponsors.extend(new_sponsors)
                    remaining = max(0, remaining - len(new_sponsors))
                    if remaining <= 0:
                        break
                return sponsors

            # Если кэш есть — используем только кэшированные данные (источники читают из cache)
            for fetch in build_sources(use_cache=True):
                if remaining <= 0:
                    break
                new_sponsors = await fetch()
                if not new_sponsors:
                    continue
                sponsors.extend(new_sponsors)
                remaining = max(0, remaining - len(new_sponsors))
                if remaining <= 0:
                    break

            # Если спонсоров нет и кэш был — выставляем completed
            requesting_all = not (no_flyer or no_subgram or no_manual)
            # if not sponsors and cache and requesting_all:
            #     await self.save_sponsors_cache(user_id, cache, completed=True)

            return sponsors

        except Exception as e:
            logger.error(f"Error getting sponsors for user {user_id}: {e}", exc_info=True)
            return []

    async def check(self, user_id: int, language_code: str, message: Message,
                    no_flyer: bool = False, no_subgram: bool = False, no_manual: bool = False,
                    done_cb: str = None,
                    max_op: int | None = None,
                    manual_unlimited: bool = False,
                    ) -> InlineKeyboardMarkup | None:

        sponsors: list[SubscribeModel] = await self.get_sponsors(
            user_id=user_id,
            message=message,
            language_code=language_code,
            no_flyer=no_flyer, no_subgram=no_subgram, no_manual=no_manual,
            max_op=max_op,
            manual_unlimited=manual_unlimited,
        )
        print(f"SPONSORS_FORMED FOR {str(user_id)}: " + str(sponsors))

        if sponsors:
            return await self.build_reply_markup(sponsors, done_cb)
        async with db.get_session() as session:
            user_repo = UserRepository(session)
            await user_repo.set_user_subbed(user_id, True, True)
        return None

    async def _set_botohub_cooldown(self, user_id: int):
        if self.botohub_cooldown <= 0:
            return
        try:
            async with redis_pool.get_connection() as conn:
                if conn is None:
                    logger.error(f"Redis connection is None for user {user_id}")
                    return
                await conn.set(
                    BOTOHUB_COOLDOWN_KEY.format(user_id),
                    int(time.time()),
                    ex=self.botohub_cooldown
                )
        except Exception as err:
            logger.error(f"Error setting botohub cooldown for {user_id}: {err}", exc_info=True)

    async def _has_botohub_cooldown(self, user_id: int) -> bool:
        if self.botohub_cooldown <= 0:
            return False
        try:
            async with redis_pool.get_connection() as conn:
                if conn is None:
                    logger.error(f"Redis connection is None for user {user_id}")
                    return False
                return bool(await conn.exists(BOTOHUB_COOLDOWN_KEY.format(user_id)))
        except Exception as err:
            logger.error(f"Error checking botohub cooldown for {user_id}: {err}", exc_info=True)
            return False

    async def fetch_botohub(self, user_id: int):
        headers = {'Content-Type': 'application/json'}
        if self.botohub_api_token:
            headers['Auth'] = self.botohub_api_token

        payload = {
            'chat_id': user_id,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.botohub_api_url, headers=headers, json=payload) as response:
                if response.status >= 400:
                    print("BOTOHUB ERROR")
                    logger.error(f"Botohub response not ok: {response.status}")
                    return []

                try:
                    data = await response.json()
                    print("BH DATA: " + str(data))
                except Exception as err:
                    logger.error(f"Failed to decode botohub response: {err}", exc_info=True)
                    return []
                if data.get('completed') or data.get('skip'):
                    return []
                tasks = data.get('tasks') or data.get('sponsors') or data.get('offers') or []
                print(f"BOTOHUB_RESP: {str(tasks)}")
                return tasks

    async def get_botohub_sponsors(self, user_id: int) -> list[SubscribeModel]:
        try:
            tasks = await self.fetch_botohub(user_id=user_id)
            sponsors: list[SubscribeModel] = []

            for task in tasks:
                sponsors.append(
                    SubscribeModel(
                        url=task,
                        is_manual=False,
                        action=ActionEnum.channel,
                    )
                )

            return sponsors
        except Exception as err:
            print("ERR WHILE FETCHING BH")
            logger.error(f"Error in get_botohub_sponsors: {err}", exc_info=True)
            return []

    async def check_botohub(self, user_id: int, done_cb: str | None = None) -> InlineKeyboardMarkup | bool:
        if await self._has_botohub_cooldown(user_id):
            print(str(user_id) + "IS ON BOTOHUB COOLDOWN")
            return None

        sponsors = await self.get_botohub_sponsors(user_id=user_id)
        print("BOTONUB SPONSORS FOR " + str(user_id) + ": " + str(sponsors))
        if sponsors:
            return await self.build_reply_markup(sponsors, done_cb)

        await self._set_botohub_cooldown(user_id)
        async with db.get_session() as session:
            user_repo = UserRepository(session)
            await user_repo.set_user_subbed(user_id, True)

        return None


op_client = OPService()
