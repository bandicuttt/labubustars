import asyncio
import config
import multiprocessing
import uvicorn

from aiogram import Dispatcher, Bot

from loader import bot, dp
from app.logger import logger
from app.schedule import scheduler_start
from app.utils.utils import check_database, AsyncSession, set_commands
from app.routers import reg_handlers
from app.middlewares import reg_middlewares
from subgram_hook import app as fastapi_app  

async def set_up_utils(dp: Dispatcher, bot: Bot):
    await scheduler_start()
    await reg_handlers(dp)
    await reg_middlewares(dp)
    await check_database()
    await set_commands()
    
    print(f'Бот запущен - @{(await bot.get_me()).username}')
    print(f'dev by @bandicuttt')

def run_fastapi():
    print(f"🚀 FastAPI host={config.FAST_API_HOST}, port={config.FAST_API_PORT}")
    uvicorn.run(
        "subgram_hook:app",  # путь до FastAPI приложения
        host=config.FAST_API_HOST,
        port=config.FAST_API_PORT,
        reload=False
    )

async def main() -> None: 
    await set_up_utils(dp=dp, bot=bot)
    
    if config.SKIP_UPDATES:
        await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    finally:
        await AsyncSession.close_session()
        await bot.session.close()

if __name__ == "__main__":
    try:
        
        if config.USE_SUBGRAM_HOOK:
            p = multiprocessing.Process(target=run_fastapi, daemon=True)
            p.start()

        asyncio.run(main())
    except KeyboardInterrupt:
        print(f'Бот выключен')
    except Exception as e:
        logger.exception("Произошла ошибка: %s", e)