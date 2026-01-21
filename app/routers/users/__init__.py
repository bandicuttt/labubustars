from .darts import darts_router
from .get_stars import get_stars_router
from .gift_miner import miner_router
from .user_profile import user_profile_router
from .top_users import top_users_router
from .tasks import get_tasks_router
from .games import games_router
from .top_up_balance import top_up_balance_router
from .withdrawal import withdrawal_user_router
from .withdrawal_gifts import withdrawal_user_gifts_router
from .channels import channel_router


def get_user_routers():
    return [
        get_stars_router,
        withdrawal_user_router,
        top_up_balance_router,
        user_profile_router,
        top_users_router,
        get_tasks_router,
        games_router,
        darts_router,
        withdrawal_user_gifts_router,
        channel_router,
        miner_router
    ]
