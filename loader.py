import config

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

def get_params() -> tuple:
    params = {
        'token': config.BOT_TOKEN,
        'default': DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=False
        )
    }

    return params

bot = Bot(**get_params())
dp = Dispatcher(storage=RedisStorage.from_url(f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"))
