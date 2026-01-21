from aiogram import Dispatcher

from .exists_user import ExistsUserMiddleware
from .throttling import ThrottlingMiddleware
from .adverts import AdvertMiddleware
from .subscribes import SubscribeMiddleware
from .on_exit import ExitMiddleware


async def reg_middlewares(dp: Dispatcher):
    ...
    # outer
    dp.update.outer_middleware(ExistsUserMiddleware())
    dp.update.outer_middleware(AdvertMiddleware())
    dp.update.middleware(SubscribeMiddleware())
    dp.update.outer_middleware(ExitMiddleware())
    # dp.update.outer_middleware(ThrottlingMiddleware)
    
    


    
