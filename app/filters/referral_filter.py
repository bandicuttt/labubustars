from app.keyboards.inline import back_kb
import config

from loader import bot

from app.database import db
from app.database.repositories import UserRepository
from app.templates.texts import min_referral_error_message, need_subscribe_our_channels_message
from app.keyboards.inline import subscribe_our_channels

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.enums.chat_member_status import ChatMemberStatus
from app.utils.utils import get_admins


class ReferralFilter(BaseFilter):
    async def __call__(self, obj: Message | CallbackQuery) -> bool:
        uid = obj.from_user.id

        if uid in get_admins():
            return True

        if not await self.check_subscribes(uid):
            if isinstance(obj, CallbackQuery):
                await obj.message.delete()

            await bot.send_photo(
                chat_id=uid,
                caption=need_subscribe_our_channels_message,
                photo=config.DEPOSIT_MENU_ID,
                reply_markup=subscribe_our_channels()
            )

        async with db.get_session() as session:
            user_repo = UserRepository(session)
            total_refed = await user_repo.get_users(count=True,ref=str(uid), subbed=True)
        
        if config.MIN_FRIENDS_FOR_WITHDRAWAL >= total_refed:
            if isinstance(obj, CallbackQuery):
                try:
                    await obj.message.delete()
                except:
                    ...
            await bot.send_photo(
                chat_id=uid,
                caption=min_referral_error_message,
                photo=config.DEPOSIT_MENU_ID,
                reply_markup=back_kb(
                    calldata='main_menu',
                    text='⬅️ В главное меню'
                ),
            )
            return False
        return True

    async def check_subscribes(self, user_id: int) -> bool:
        try:
            return not (await bot.get_chat_member(
                chat_id=config.MAIN_CHANNEL_ID,
                user_id=user_id
            )).status in [
                ChatMemberStatus.LEFT,
                ChatMemberStatus.KICKED,
            ]
        except:
            return True