import asyncio
import os
import aiofiles
import json
import config

from sqlalchemy.sql.expression import delete

from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import select, or_, func, text, desc, String
from sqlalchemy.orm import aliased

from datetime import datetime, timedelta

from loader import bot

from app.logger import logger
from app.utils.misc_function import get_time_now
from app.database import models, redis_pool

USER_TTL_SECONDS = 10 * 24 * 3600  # 10 дней активности 

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_user(self, **kwargs):
        user = models.User(**kwargs)
        try:
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return None

        # Работа с Redis после успешного коммита
        async with redis_pool.get_connection() as redis:
            redis_key = f"user_activity:{user.user_id}"
            await redis.set(redis_key, get_time_now().timestamp(), ex=USER_TTL_SECONDS)
            await redis.zadd("user_last_activity", {user.user_id: get_time_now().timestamp()})

        return user

    async def get_user_position(self, user_id: int, period: str = 'today') -> tuple[int, int]:
        """Get user position in rating and total referrals count"""
        referred = aliased(models.User, name='referred')

        # Count users who have been referred by others
        referrers = select(
            models.User.user_id,
            func.count(referred.id).label('ref_count')
        ).select_from(models.User).join(
            referred,
            referred.ref == func.cast(models.User.user_id, String),
        ).group_by(
            models.User.user_id
        )

        if period == 'today':
            yesterday = get_time_now() - timedelta(days=1)
            referrers = referrers.where(referred.created_at >= yesterday)

        # Get all users ordered by referral count
        result = await self.session.execute(
            referrers.order_by(desc('ref_count'))
        )
        all_users = result.all()
        
        # Find user position and their referral count
        for position, (uid, ref_count) in enumerate(all_users, 1):
            if uid == user_id:
                return position, ref_count
                
        return len(all_users) + 1, 0  # If user has no referrals

    async def get_user(self, user_id: int):
        result = await self.session.execute(select(models.User).where(models.User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_all_users(self, count: bool = False):
        query = select(func.count()).select_from(models.User) if count else select(models.User)
        result = await self.session.execute(query)
        return result.scalars().all() if not count else result.scalar()
    
    async def get_referral_stats(self, user_id: int) -> dict:
        """
        Получает статистику по рефералам пользователя
        """
        # Получаем всех рефералов
        referrals_query = select(models.User).where(
            models.User.ref == str(user_id)
        )
        result = await self.session.execute(referrals_query)
        all_referrals = result.scalars().all()
        
        total_referrals = len(all_referrals)
        
        # Активные рефералы (подписанные)
        active_referrals = [r for r in all_referrals if r.subbed]
        total_active = len(active_referrals)
        
        # Живые рефералы (без блокировки)
        alive_referrals = [r for r in all_referrals if r.block_date is None]
        total_alive = len(alive_referrals)
        
        # Среднее время между рефералами
        avg_time_between = None
        if len(all_referrals) > 1:
            # Сортируем по дате создания
            sorted_referrals = sorted(all_referrals, key=lambda x: x.created_at)
            time_diffs = []
            
            for i in range(1, len(sorted_referrals)):
                time_diff = (sorted_referrals[i].created_at - sorted_referrals[i-1].created_at).total_seconds()
                time_diffs.append(time_diff)
            
            if time_diffs:
                avg_time_between = sum(time_diffs) / len(time_diffs)
        
        return {
            'total_referrals': total_referrals,
            'total_active': total_active,
            'total_alive': total_alive,
            'avg_time_between': avg_time_between  # в секундах
        }

    async def get_users(self,count: bool = False, **kwargs):
        query = select(func.count()).select_from(models.User) if count else select(models.User)

        for key, value in kwargs.items():
            if hasattr(models.User, key):
                query = query.where(getattr(models.User, key) == value)

        result = await self.session.execute(query)
        return result.scalars().all() if not count else result.scalar()

    async def update_user(self, user_id: int, important_action: bool = False, **kwargs):
        user = await self.get_user(user_id)

        for key, value in kwargs.items():
            setattr(user, key, value)

        if important_action:
            redis_key = f"user_activity:{user_id}"

            async with redis_pool.get_connection() as r:
                was_active = await r.exists(redis_key)
                await r.set(redis_key, get_time_now().timestamp(), ex=USER_TTL_SECONDS)
                await r.zadd("user_last_activity", {user_id: get_time_now().timestamp()})

            user.last_activity=get_time_now()

            # Если юзер ушёл в инактив
            if not was_active:

                user.reactivation_count += 1
                user.is_inactive = False

                if user.ref and str(user.ref).isdigit():

                    referrer = await self.session.execute(
                        select(models.User).where(models.User.user_id == int(user.ref))
                    )
                    referrer_obj = referrer.scalars().first()

                    if referrer_obj:
                        referrer_obj.balance += 2
                        self.session.add(referrer_obj)

                        with suppress(TelegramBadRequest):
                            await bot.send_message(
                                chat_id=user.ref,
                                text='🎉 Вы получили 2 ⭐️ за возвращение пользователя!'
                            )

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        return user

    async def get_inactive_users(self, referrer_user_id: str):
        CACHE_TTL_SECONDS = 30*60
        cache_key = f"inactive_users_text:{referrer_user_id}"

        async with redis_pool.get_connection() as r:
            # cached = await r.get(cache_key)
            # if cached:
            #     data = json.loads(cached)
            #     return data['text'], data['total_reactivations']

            threshold = (get_time_now() - timedelta(days=10)).timestamp()
            inactive_user_ids_bytes = await r.zrangebyscore("user_last_activity", 0, threshold)
            inactive_user_ids = [int(uid.decode('utf-8')) if isinstance(uid, bytes) else int(uid) for uid in inactive_user_ids_bytes]

            if not inactive_user_ids:
                return "", 0

            query = await self.session.execute(
                select(models.User.user_id, models.User.user_fullname, models.User.user_name, models.User.reactivation_count)
                .where(models.User.ref == referrer_user_id)
            )
            rows = query.all()

            # Формируем список строк с html-ссылками
            lines = []
            total_reactivations = 0

            for user_id, fullname, username, reac_count in rows:
                display_name = f'@{username}' if username else fullname
                line = f'<a href="tg://user?id={user_id}">{display_name} | {reac_count} 🔁</a>'
                lines.append(line)
                total_reactivations += reac_count

            text = "\n".join(lines)

            # Кэшируем JSON с текстом и суммой
            cache_data = json.dumps({
                'text': text,
                'total_reactivations': total_reactivations
            })
            await r.set(cache_key, cache_data, ex=CACHE_TTL_SECONDS)

            return text, total_reactivations

    async def add_user_balance_ref(self, user_id: int):
        user = await self.get_user(user_id)
        if user:
            return await self.update_user(
                user_id=user_id,
                important_action=True,
                balance=user.balance + 3,
            )
        return None

    async def get_count_users_offsets(
        self,
        offset1: datetime,
        offset2: datetime,
        **kwargs
    ):
        query = select(func.count()).select_from(models.User)

        conditions = [
            models.User.created_at > offset2,
            models.User.created_at < offset1
        ]

        for key, value in kwargs.items():
            if hasattr(models.User, key):
                if key == 'block_date' and value:
                    conditions.append(models.User.block_date.isnot(None))
                else:
                    conditions.append(getattr(models.User, key) == value)

        query = query.where(*conditions)

        result = await self.session.execute(query)
        return result.scalar()

    async def get_count_users_since(
        self,
        since: datetime,
        until: datetime | None = None,
        **kwargs
    ):
        query = select(func.count()).select_from(models.User)

        conditions = [models.User.created_at >= since]
        if until is not None:
            conditions.append(models.User.created_at < until)

        for key, value in kwargs.items():
            if hasattr(models.User, key):
                if key == 'block_date' and value:
                    conditions.append(models.User.block_date.isnot(None))
                else:
                    conditions.append(getattr(models.User, key) == value)

        query = query.where(*conditions)

        result = await self.session.execute(query)
        return result.scalar()

    async def get_refs_count(self, ref: str | None, offset1: datetime, offset2: datetime):
        query = select(func.count()).select_from(models.User)

        conditions = [
            models.User.created_at > offset2,
            models.User.created_at < offset1
        ]

        if ref is None:
            conditions.append(models.User.ref.is_(None))
        elif ref == 'users':
            conditions.append(models.User.ref.op('~')('^[a-zA-Z]+$'))
        elif ref == 'sponsors':
            conditions.append(models.User.ref.op('~')('^[0-9]*$'))

        query = query.where(*conditions)

        result = await self.session.execute(query)
        return result.scalar()

    async def get_refs_total_count(self, ref: str | None):
        query = select(func.count()).select_from(models.User)

        if ref is None:
            query = query.where(models.User.ref.is_(None))
        elif ref == 'users':
            query = query.where(models.User.ref.op('~')('^[a-zA-Z]+$'))
        elif ref == 'sponsors':
            query = query.where(models.User.ref.op('~')('^[0-9]*$'))

        result = await self.session.execute(query)
        return result.scalar()

    async def get_op_count(
        self,
        op_num: int,
        ref: str | None = None,
        since: datetime | None = None,
    ) -> int:
        query = select(func.count()).select_from(models.User)
        conditions = [models.User.darts_op_count >= op_num]

        if ref is not None:
            conditions.append(models.User.ref == ref)

        if since is not None:
            conditions.append(models.User.created_at >= since)

        result = await self.session.execute(query.where(*conditions))
        return result.scalar()

    async def get_user_ids_mailing(self, is_vip: bool, is_premium: bool) -> List[int]:
        query = select(models.User.user_id)

        if is_premium:
            query = query.where(models.User.is_premium == True)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_unique_refs(self):
        # Получаем рефералы из таблицы Referrals
        referrals_query = select(
            models.Referral.ref,
            models.Referral.total_visits,
        ).order_by(models.Referral.id.desc())
        referrals_result = await self.session.execute(referrals_query)
        referrals_data = [{'ref': row[0], 'count': row[1]} for row in referrals_result]

        # # Получаем рефералы из таблицы Users
        # users_query = select(models.User.ref).distinct()
        # users_result = await self.session.execute(users_query)
        # refs = [row[0] for row in users_result if row[0] is not None]

        # # Фильтруем рефералы из Users
        # filtered_refs = []
        # for ref in refs:
        #     if re.match(r'^[a-zA-Zа-яА-ЯёЁ]+$', ref):  # Только буквы
        #         filtered_refs.append(ref)
        #     elif re.match(r'^[a-zA-Zа-яА-ЯёЁ0-9]+$', ref):  # Буквы и цифры
        #         filtered_refs.append(ref)
        #     elif re.match(r'^\d+$', ref):  # Только цифры
        #         filtered_refs.append(ref)

        # # Считаем количество для рефералов из Users
        # ref_counts = Counter(filtered_refs)
        # users_data = [{'ref': ref, 'count': count} for ref, count in ref_counts.items()]

        # # Сортируем данные из Users
        # users_data.sort(key=lambda x: x['ref'])
        # users_data.sort(key=lambda x: (
        #     0 if re.match(r'^[a-zA-Zа-яА-ЯёЁ]+$', x['ref']) else
        #     1 if re.match(r'^[a-zA-Zа-яА-ЯёЁ0-9]+$', x['ref']) else
        #     2
        # ))

        # Объединяем данные, сначала Referrals, потом Users
        # Исключаем дубликаты из Users, если они уже есть в Referrals
        referral_refs = {item['ref'] for item in referrals_data}
        # filtered_users_data = [item for item in users_data if item['ref'] not in referral_refs]

        return referrals_data
    
    async def get_top_referrals(self, period: str = 'today') -> list[tuple[str, int]]:
        """Get top 10 users by number of referrals for specified period"""
        referred = aliased(models.User, name='referred')

        # Count users who have been referred by others
        referrers = select(
            models.User.user_fullname,
            func.count(referred.id).label('ref_count')
        ).select_from(models.User).join(
            referred,
            referred.ref == func.cast(models.User.user_id, String),
        ).group_by(
            models.User.user_id,
            models.User.user_fullname
        )

        if period == 'today':
            yesterday = get_time_now() - timedelta(days=1)
            referrers = referrers.where(referred.created_at >= yesterday)

        result = await self.session.execute(
            referrers.order_by(desc('ref_count')).limit(10)
        )
        return result.all()

    async def create_dump(self, dump_dir='dumps', only_users_and_chats=False):
        os.makedirs(dump_dir, exist_ok=True)
        current_time = get_time_now().strftime("%Y_%m")

        users_dump_file = os.path.join(dump_dir, f'users_dump_{current_time}.txt')
        user_chats_dump_file = os.path.join(dump_dir, f'user_chats_dump_{current_time}.txt')
        users_and_chats_dump_file = os.path.join(dump_dir, f'users_and_chats_dump_{current_time}.txt')
        db_dump_file = os.path.join(dump_dir, f'database_dump_{current_time}.sql')

        # Create text dumps
        users = [i.user_id for i in await self.get_all_users()]
        chats = [i.chat_id for i in (await self.session.execute(select(models.UserChat))).scalars().all()]
        
        async with aiofiles.open(users_dump_file, 'w', encoding='utf-8') as f:
            for user in users:
                await f.write(str(user) + '\n')

        async with aiofiles.open(user_chats_dump_file, 'w', encoding='utf-8') as f:
            for user in chats:
                await f.write(str(user) + '\n')
            
        async with aiofiles.open(users_and_chats_dump_file, 'w', encoding='utf-8') as f:
            for user in (users + chats):
                await f.write(str(user) + '\n')

        dump_command = f'pg_dump -h {config.POSTGRES_HOST} -U {config.POSTGRES_USER} -F p -f "{db_dump_file}" {config.POSTGRES_DB}'
        
        process = await asyncio.create_subprocess_shell(
            dump_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"PGPASSWORD": config.POSTGRES_PASSWORD}
        )
        await process.communicate()

        if only_users_and_chats:
            return users_and_chats_dump_file

        return users_dump_file, user_chats_dump_file, users_and_chats_dump_file, db_dump_file

    async def set_user_subbed(self, user_id: int, subbed: bool, second: bool = None):
        if subbed:
            if second is not None:
                return await self.update_user(user_id, subbed=True, subbed_second=second)
            return await self.update_user(user_id, subbed=True)
        else:
            return await self.update_user(user_id, subbed=False, subbed_second=False)
