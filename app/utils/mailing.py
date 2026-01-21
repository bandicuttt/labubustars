import asyncio

from datetime import datetime
from typing import List
from aiogram import Bot, exceptions
from aiogram.types import Message

from app.utils.misc_function import get_time_now
from app import templates
from app.pydantic_models.mailing import MailingData
from app.database import repositories
from app.utils.utils import get_admins

from app.database import db


class Mailer:
    def __init__(self, bot: Bot, data: MailingData):
        self.bot = bot
        self.data = data
        self.successful_send = 0
        self.error_send = 0
        self.successful_pin = 0
        self.error_pin = 0
        self.range = 20

    async def get_targets(self, session) -> List[int]:
        user_repo = repositories.user_repo.UserRepository(session)
        targets = await user_repo.get_user_ids_mailing(
            is_vip=self.data.is_vip,
            is_premium=self.data.is_premium
        )

        if self.data.is_chats:
            chats_repo = repositories.chat_repo.UserChatRepository(session)
            chats = [i.chat_id for i in await chats_repo.get_all_chats(count=False)]
            targets += chats

        # Исключаем админов из рассылки
        for chat_id in get_admins():
            targets.remove(chat_id)

        return targets

    async def send_message(self, chat_id: int):
        try:
            m = await self.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=self.data.from_chat_id,
                message_id=self.data.message_id,
                reply_markup=self.data.reply_markup
            )
            self.successful_send += 1
            return m.message_id
        except exceptions.TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            return await self.send_message(chat_id)
        except exceptions.TelegramBadRequest as e:
            self.error_send += 1
        except Exception as e:
            self.error_send += 1

    async def pin_message(self, chat_id: int, message_id: int):
        if self.data.is_pin and chat_id > 0:
            try:
                await self.bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=message_id,
                    disable_notification=False
                )
                self.successful_pin += 1
            except exceptions.TelegramBadRequest:
                self.error_pin += 1
            except Exception:
                self.error_pin += 1

    def get_execution_time(self, start_time: datetime) -> str:
        end_time = get_time_now()
        execution_time = end_time - start_time

        total_seconds = int(execution_time.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f'{hours}:{minutes}:{seconds}'

    async def mail(self):
        m: Message = await self.bot.send_message(
            chat_id=self.data.from_chat_id,
            text=templates.texts.admin_mailing_start
        )
        start_time = get_time_now()
        async with db.get_session() as session:
            targets = await self.get_targets(session)

        total_targets = len(targets)
        for i in range(0, total_targets, self.range):
            batch = targets[i:i + self.range]
            tasks = []

            for chat_id in batch:
                message_id = await self.send_message(chat_id)
                if message_id:
                    tasks.append(self.pin_message(chat_id, message_id))

            await asyncio.gather(*tasks)

            execution_time = self.get_execution_time(start_time=start_time)
            try:
                await m.edit_text(
                    text=templates.texts.admin_mailing_process.format(
                        total_send=min(i + self.range, total_targets),
                        targets=total_targets,
                        successful_send=self.successful_send,
                        error_send=self.error_send,
                        successful_pin=self.successful_pin,
                        error_pin=self.error_pin,
                        execution_time=execution_time
                    )
                )
            except Exception(
                exceptions.TelegramBadRequest,
                exceptions.TelegramRetryAfter,
            ):
                pass
            except Exception:
                pass

        await m.edit_text(
            text=templates.texts.admin_mailing_finish.format(
                successful_send=self.successful_send,
                error_send=self.error_send,
                successful_pin=self.successful_pin,
                error_pin=self.error_pin,
                execution_time=self.get_execution_time(start_time=start_time)
            )
        )
        return {
            "successful_send": self.successful_send,
            "error_send": self.error_send,
            "successful_pin": self.successful_pin,
            "error_pin": self.error_pin,
            "execution_time": self.get_execution_time(start_time=start_time)
        }