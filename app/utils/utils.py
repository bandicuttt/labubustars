import re
import aiohttp
import random
import string

from functools import lru_cache
from datetime import datetime, timedelta

from typing import Optional

import config
from app.database.models.user import User
from config import *
from loader import bot

from aiogram import Bot, types
from aiogram.exceptions import TelegramNetworkError, TelegramBadRequest
from aiogram.enums.chat_member_status import ChatMemberStatus
from aiogram.exceptions import (
    TelegramUnauthorizedError,
    TelegramNotFound,
    TelegramForbiddenError,
)
from sqlalchemy import select

from app.utils.dice_data import (
    darts_value,
    basketball_value,
    bowling_value,
    slot_machine_value,
    football_value,
    win_multiplier_map
)

from contextlib import suppress
from pathlib import Path

from app import templates
from app.database import db, repositories, redis_pool
from app.utils.stats import audit_stat
from app.database import models
from app.database.models.subsribes import Subscribe
from app.utils.misc_function import get_time_now
from app.templates.texts import push_notification_message
from app.keyboards.inline import push_notification_kb, main_user
from app.templates.posts_for_channel import POSTS_DATA

gifts_dir = Path('gifts')

admin_commands = [
    types.BotCommand(command="/start", description="Перезапустить"),
    types.BotCommand(command="/admin", description="Админ Панель"),
    types.BotCommand(command="/clear_jackpot", description="Очистить JackPot"),
    types.BotCommand(command="/set_channel", description="Установить канал"),
]

async def send_channel_posts():
    """Отправляет случайный пост в канал с автоматическим определением типа контента"""
    post = random.choice(POSTS_DATA)

    if post.get('media'):
        # Определяем тип медиа по расширению файла
        media_path = post['media']
        
        if media_path.endswith(('.jpg', '.jpeg', '.png')):
            await bot.send_photo(
                chat_id=MAIN_CHANNEL_ID,
                photo=types.FSInputFile(media_path),
                caption=post.get('caption', ''),
                reply_markup=post.get('reply_markup')
            )
        elif media_path.endswith(('.mp4', '.gif')):
            await bot.send_animation(
                chat_id=MAIN_CHANNEL_ID,
                animation=types.FSInputFile(media_path),
                caption=post.get('caption', ''),
                reply_markup=post.get('reply_markup')
            )
    else:
        await bot.send_message(
            chat_id=MAIN_CHANNEL_ID,
            text=post.get('caption', ''),
            reply_markup=post.get('reply_markup'),
        )

async def send_push_to_inactive_users():
    """
    Находит пользователей, ставших неактивными ровно 24 часа назад,
    и отправляет им пуш-сообщение.
    """

    threshold_time = get_time_now() - timedelta(hours=24)

    async with db.get_session() as session:
        query = await session.execute(
            select(User)
            .where(User.last_activity < threshold_time)
        )
    users_to_notify: list[User] = query.scalars().all()

    for user in users_to_notify:
        try:
            await bot.send_photo(
                photo=TASKS_MAIN_MENU_ID,
                chat_id=user.user_id,
                caption=push_notification_message,
                reply_markup=push_notification_kb(
                    BOT_USERNAME,
                    user.user_id
                )
            )
        except Exception as e:
           ...


async def set_commands():
    for admin in get_admins():
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=types.BotCommandScopeChat(chat_id=admin)
            )
        except Exception as e:
            print(e)
            pass

async def daily_backup():
    today, week_ago, month_ago, year_ago = get_times()
    yesterday = today - timedelta(days=1)
    admins = get_admins()

    async with db.get_session() as session:
        user_repo = repositories.UserRepository(session)
        dump_date = get_time_now().strftime("%Y.%m.%d")

        with suppress(TelegramBadRequest, TelegramNetworkError):
            for admin in admins:
                await bot.send_photo(
                    chat_id=admin,
                    photo=types.FSInputFile(path=await audit_stat(yesterday)),
                    disable_notification=True
                )
                await bot.send_message(
                    chat_id=admin,
                    text=templates.texts.admin_stats_message.format(
                        date_frame=yesterday.strftime('%d.%m.%Y'),
                        **await get_stat(yesterday, offset1=today)
                    ),
                    disable_notification=True
                )

            for file in await user_repo.create_dump():
                for admin in admins:
                    await bot.send_document(
                        chat_id=admin,
                        document=types.FSInputFile(path=file),
                        caption=dump_date,
                        disable_notification=True
                    )


def is_valid_link(text: str) -> bool:
    pattern = r'^(http://|https://|t\.me/|https://t\.me/)([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(/[^\s]*)?$'
    return bool(re.match(pattern, text))

async def check_database():
    async with db.get_session() as session:
        await db.check_and_create_tables()

def clear_html(get_text: str) -> str:
    if get_text is not None:
        if "</" in get_text: get_text = get_text.replace("<", "*")
        if "<" in get_text: get_text = get_text.replace("<", "*")
        if ">" in get_text: get_text = get_text.replace(">", "*")
    else:
        get_text = ""

    return get_text

def get_admins():
    return ADMINS

def get_times(current_time: datetime = None):
    if current_time is None:
        current_time = get_time_now()
        
    today = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    year_ago = today - timedelta(days=365)
    
    return today, week_ago, month_ago, year_ago

def datetime_to_strftime(obj: datetime):
    return obj.strftime('%Y-%m-%d %H:%M:%S')

def get_ref(message: types.Message, check: bool=True) -> Optional[str]:
    if check and not message.text.startswith('/start'):

        return

    if args := message.text.split()[1:]:
        
        return args[0]

async def get_ref_stat_new(ref: str):
    today = get_times()[0]  # Берем только сегодняшнюю дату
    
    async with db.get_session() as session:
        user_repo = repositories.UserRepository(session)
        referral_repo = repositories.ReferralRepository(session)
        
        # Получаем данные из Referral модели
        referral = await referral_repo.get_referral_by_ref(ref)
        total_clicks = referral.total_visits if referral else 0
        ref_price = referral.price if referral else 0
        
        # Базовые метрики по пользователям
        uniq_users = await user_repo.get_users(count=True, ref=ref)
        total_uniq_live_users = await user_repo.get_users(count=True, ref=ref, block_date=None)
        total_subscribed = await user_repo.get_users(count=True, ref=ref, subbed=True)
        total_subscribed_second = await user_repo.get_users(count=True, ref=ref, subbed=True, subbed_second=True)
        total_premium_users = await user_repo.get_users(count=True, ref=ref, is_premium=True)
        
        # Метрики за сегодня
        offset1 = get_time_now()
        total_uniq_users_today = await user_repo.get_count_users_since(
            since=today,
            ref=ref
        )
        total_uniq_users_subscribed_today = await user_repo.get_count_users_since(
            since=today,
            ref=ref,
            subbed=True
        )
        total_uniq_users_subscribed_second_today = await user_repo.get_count_users_since(
            since=today,
            ref=ref,
            subbed=True,
            subbed_second=True
        )
        total_uniq_live_users_today = await user_repo.get_count_users_since(
            since=today,
            ref=ref,
            block_date=None
        )

        total_op_counts_today = {
            'op1_today': await user_repo.get_op_count(op_num=1, ref=ref, since=today),
            'op2_today': await user_repo.get_op_count(op_num=2, ref=ref, since=today),
            'op3_today': await user_repo.get_op_count(op_num=3, ref=ref, since=today),
            'op4_today': await user_repo.get_op_count(op_num=4, ref=ref, since=today),
            'op5_today': await user_repo.get_op_count(op_num=5, ref=ref, since=today),
            'op6_plus_today': await user_repo.get_op_count(op_num=6, ref=ref, since=today),
        }

        total_op_percents_today = {
            'op1_today_percent': (total_op_counts_today['op1_today'] / total_uniq_users_today) * 100 if total_uniq_users_today > 0 else 0,
            'op2_today_percent': (total_op_counts_today['op2_today'] / total_uniq_users_today) * 100 if total_uniq_users_today > 0 else 0,
            'op3_today_percent': (total_op_counts_today['op3_today'] / total_uniq_users_today) * 100 if total_uniq_users_today > 0 else 0,
            'op4_today_percent': (total_op_counts_today['op4_today'] / total_uniq_users_today) * 100 if total_uniq_users_today > 0 else 0,
            'op5_today_percent': (total_op_counts_today['op5_today'] / total_uniq_users_today) * 100 if total_uniq_users_today > 0 else 0,
            'op6_plus_today_percent': (total_op_counts_today['op6_plus_today'] / total_uniq_users_today) * 100 if total_uniq_users_today > 0 else 0,
        }

        total_op_counts = {
            'op1': await user_repo.get_op_count(op_num=1, ref=ref),
            'op2': await user_repo.get_op_count(op_num=2, ref=ref),
            'op3': await user_repo.get_op_count(op_num=3, ref=ref),
            'op4': await user_repo.get_op_count(op_num=4, ref=ref),
            'op5': await user_repo.get_op_count(op_num=5, ref=ref),
            'op6_plus': await user_repo.get_op_count(op_num=6, ref=ref),
        }

        total_op_percents = {
            'op1_percent': (total_op_counts['op1'] / uniq_users) * 100 if uniq_users > 0 else 0,
            'op2_percent': (total_op_counts['op2'] / uniq_users) * 100 if uniq_users > 0 else 0,
            'op3_percent': (total_op_counts['op3'] / uniq_users) * 100 if uniq_users > 0 else 0,
            'op4_percent': (total_op_counts['op4'] / uniq_users) * 100 if uniq_users > 0 else 0,
            'op5_percent': (total_op_counts['op5'] / uniq_users) * 100 if uniq_users > 0 else 0,
            'op6_plus_percent': (total_op_counts['op6_plus'] / uniq_users) * 100 if uniq_users > 0 else 0,
        }

        # Вычисляем цену за живого пользователя
        cost_for_per_uniq_live_user = (
            round(ref_price / total_uniq_live_users, 2)
            if total_uniq_live_users > 0 and ref_price
            else 0
        )

        total_sub_precent = (total_subscribed / uniq_users) * 100 if uniq_users > 0 else 0
        total_sub_second_precent = (total_subscribed_second / uniq_users) * 100 if uniq_users > 0 else 0
        total_prem_precent = (total_premium_users / uniq_users) * 100 if uniq_users > 0 else 0
        total_sub_precent_today = (total_uniq_users_subscribed_today / total_uniq_users_today) * 100 if total_uniq_users_today > 0 else 0
        total_sub_second_precent_today = (total_uniq_users_subscribed_second_today / total_uniq_users_today) * 100 if total_uniq_users_today > 0 else 0

        return {
            'total_clicks': total_clicks,
            'total_sub_precent': total_sub_precent,
            'total_sub_second_precent': total_sub_second_precent,
            'total_prem_precent': total_prem_precent,
            'total_sub_precent_today': total_sub_precent_today,
            'total_sub_second_precent_today': total_sub_second_precent_today,
            'uniq_users': uniq_users,
            'total_uniq_live_users': total_uniq_live_users,
            'total_subscribed': total_subscribed,
            'total_subscribed_second': total_subscribed_second,
            'total_premium_users': total_premium_users,
            'total_uniq_users_today': total_uniq_users_today,
            'total_uniq_users_subscribed_today': total_uniq_users_subscribed_today,
            'total_uniq_users_subscribed_second_today': total_uniq_users_subscribed_second_today,
            'total_uniq_live_users_today': total_uniq_live_users_today,
            'total_subscribed_today': total_uniq_users_subscribed_today,
            'cost_for_per_uniq_live_user': cost_for_per_uniq_live_user,
            'ref_price': ref_price,
            **total_op_counts_today,
            **total_op_counts,
            **total_op_percents_today,
            **total_op_percents,
            'total_subbed_percent': total_sub_precent,
            'total_subbed_percent_today': total_sub_precent_today,
        }


async def get_stat(timeframe: datetime, offset1: datetime | None = None):

    if offset1 is None:
        offset1 = get_time_now()

    async with db.get_session() as session:
        user_repo: repositories.UserRepository = repositories.UserRepository(session)
        chat_repo = repositories.UserChatRepository(session)
        action_history_repo = repositories.ActionHistoryRepository(session)

        total_users = await user_repo.get_all_users(count=True)
        total_alive = await user_repo.get_users(block_date=None, count=True)
        total_dead = total_users - total_alive
        total_chats = await chat_repo.get_all_chats(count=True)


        total_users_dateframe = await user_repo.get_count_users_offsets(offset1=offset1, offset2=timeframe)
        total_users_dead_dateframe = await user_repo.get_count_users_offsets(offset1=offset1, offset2=timeframe, block_date=True)
        total_alive_dateframe = total_users_dateframe - total_users_dead_dateframe

        total_no_ref_dateframe = await user_repo.get_refs_count(offset1=offset1, offset2=timeframe, ref=None)
        total_ref_dateframe = await user_repo.get_refs_count(offset1=offset1, offset2=timeframe, ref='users')
        total_ref_users_dateframe = await user_repo.get_refs_count(offset1=offset1, offset2=timeframe, ref='sponsors')
        
        total_success_downloads_dateframe = await action_history_repo.get_count_action_history_offsets(offset1=offset1, offset2=timeframe, action_type='success_download')
        total_error_downloads_dateframe = await action_history_repo.get_count_action_history_offsets(offset1=offset1, offset2=timeframe, action_type='error_download')
        total_chats_dateframe = await chat_repo.get_count_chats_offsets(offset1=offset1, offset2=timeframe)
        total_chats_alive_dateframe = await chat_repo.get_count_chats_offsets(offset1=offset1, offset2=timeframe, block_date=None)
        total_chats_dead_dateframe = total_chats_dateframe - total_chats_alive_dateframe
        total_chats_call_dateframe = await action_history_repo.get_count_action_history_offsets(offset1=offset1, offset2=timeframe, action_type='chat_call')
        total_chats_call_no_reg_dateframe =await action_history_repo.get_count_action_history_offsets(offset1=offset1, offset2=timeframe, action_type='chat_call_no_reg')
        total_subbed_dateframe = await user_repo.get_count_users_offsets(offset1=offset1, offset2=timeframe, subbed=True)

        total_op_counts = {
            'op1': await user_repo.get_op_count(op_num=1),
            'op2': await user_repo.get_op_count(op_num=2),
            'op3': await user_repo.get_op_count(op_num=3),
            'op4': await user_repo.get_op_count(op_num=4),
            'op5': await user_repo.get_op_count(op_num=5),
            'op6_plus': await user_repo.get_op_count(op_num=6),
        }
        total_subbed = await user_repo.get_users(count=True, subbed=True)
        total_op_percents = {
            'op1_percent': (total_op_counts['op1'] / total_users) * 100 if total_users > 0 else 0,
            'op2_percent': (total_op_counts['op2'] / total_users) * 100 if total_users > 0 else 0,
            'op3_percent': (total_op_counts['op3'] / total_users) * 100 if total_users > 0 else 0,
            'op4_percent': (total_op_counts['op4'] / total_users) * 100 if total_users > 0 else 0,
            'op5_percent': (total_op_counts['op5'] / total_users) * 100 if total_users > 0 else 0,
            'op6_plus_percent': (total_op_counts['op6_plus'] / total_users) * 100 if total_users > 0 else 0,
        }
        total_subbed_percent = (total_subbed / total_users) * 100 if total_users > 0 else 0
        total_subbed_percent_dateframe = (
            (total_subbed_dateframe / total_users_dateframe) * 100
            if total_users_dateframe > 0
            else 0
        )

        return {
            'total_users': total_users,
            'total_alive': total_alive,
            'total_dead': total_dead,
            'total_chats': total_chats,
            'total_users_dateframe': total_users_dateframe,
            'total_users_dead_dateframe': total_users_dead_dateframe,
            'total_alive_dateframe': total_alive_dateframe,
            'total_no_ref_dateframe': total_no_ref_dateframe,
            'total_ref_dateframe': total_ref_dateframe,
            'total_ref_users_dateframe': total_ref_users_dateframe,
            'total_success_downloads_dateframe': total_success_downloads_dateframe,
            'total_error_downloads_dateframe': total_error_downloads_dateframe,
            'total_chats_dateframe': total_chats_dateframe,
            'total_chats_alive_dateframe': total_chats_alive_dateframe,
            'total_chats_dead_dateframe': total_chats_dead_dateframe,
            'total_chats_call_dateframe': total_chats_call_dateframe,
            'total_chats_call_no_reg_dateframe': total_chats_call_no_reg_dateframe,
            'total_subscribed_dateframe': total_subbed_dateframe,
            'total_subbed_percent_dateframe': total_subbed_percent_dateframe,
            'total_subscribed': total_subbed,
            'total_subbed_percent': total_subbed_percent,
            **total_op_counts,
            **total_op_percents,
        }


class AsyncSession():
    _session: Optional[aiohttp.ClientSession] = None

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            cls._session = aiohttp.ClientSession()
        return cls._session

    @classmethod
    async def close_session(cls):
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None

@lru_cache
def validate_botstat_token(token: str):
    if len(token.split('-')) != 5:
        raise ValueError


async def check_subs():
    return

async def check_subscribe_channel(user_id: int, sub: Subscribe):
    try:
        member = await bot.get_chat_member(
            chat_id=sub.access,
            user_id=user_id,
        )
        is_subscribed = member.status not in (
            ChatMemberStatus.LEFT,
            ChatMemberStatus.KICKED,
            ChatMemberStatus.RESTRICTED
        )
        if not is_subscribed:
            return sub, sub
        return None, sub
    except Exception as e:
        print(str(e))
        return None, sub


async def check_for_bot(user_id: int, sub: models.Subscribe) -> Optional[models.Subscribe]:
    try:
        bot_ = Bot(sub.access, session=bot.session)
        await bot_.send_chat_action(user_id, 'typing')
        return None, sub
    except TelegramUnauthorizedError:
        async with db.get_session() as session:
            sub_repo = repositories.SubscribeRepository(session)
            await sub_repo.update_subscribe(sub_id=sub.id, status=False)
        return None, sub
    except (
        TelegramNotFound,
        TelegramBadRequest,
        TelegramForbiddenError,
    ):
        return sub, sub
    except:
        return None, sub


def check_win(game: str, value: int) -> float | bool:
    """
    Check if the game value results in a win and return the multiplier.
    
    Args:
        game (str): The game type (e.g., 'slots')
        value (int): The game value to check
        
    Returns:
        float | bool: The win multiplier if it's a winning combination, False otherwise
    """
    if game == 'darts':
        if value not in darts_value:
            return False
        return darts_value[value]

    if game == 'bowling':
        if value not in bowling_value:
            return False
        return bowling_value[value]

    if game == 'football':
        if value not in football_value:
            return False
        return football_value[value]

    if game == 'basketball':
        if value not in basketball_value:
            return False
        return basketball_value[value]

    if game == 'slots':
        if value not in slot_machine_value:
            return False
            
        combination = slot_machine_value[value]
        
        # Check for three of a kind
        if combination[0] == combination[1] == combination[2]:
            return win_multiplier_map[combination[0]]["three_of_a_kind"]
        
        # Check for two of a kind in any position
        if combination[1] == combination[2]:  # Last two match
            return win_multiplier_map[combination[1]]["two_of_a_kind"]
        elif combination[0] == combination[1]:  # First two match
            return win_multiplier_map[combination[0]]["two_of_a_kind"]
        elif combination[0] == combination[2]:  # First and last match
            return win_multiplier_map[combination[0]]["two_of_a_kind"]
        
    return False

async def get_gifts():
    available_gifts = await bot.get_available_gifts()
    gifts_data = []
    for gift in available_gifts.gifts:
        file_name = f"{gift.id}.jpg"
        await bot.download(
            file=gift.sticker.thumbnail.file_id,
            destination=gifts_dir.joinpath(file_name).absolute(),
        )
        gifts_data.append({
            'gift_star_count': gift.star_count,
            'file_id': gift.sticker.thumbnail.file_id,
            'gift_id': gift.id,
            'gifts_count': gift.remaining_count
        })

    gifts_data = sorted(gifts_data, key=lambda x: x['gift_star_count'])

    for index, gift in enumerate(gifts_data, start=1):
        gift['id'] = index

    return [
            {'total': len(available_gifts.gifts)},
            {'gifts': gifts_data}
        ]


async def send_main_menu_util(message: types.Message):
    await message.answer_photo(
        photo=config.MAIN_MENU_ID,
        caption=templates.texts.start_message,
        reply_markup=main_user()
    )
