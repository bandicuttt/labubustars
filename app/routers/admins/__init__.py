from .gift_moderation import gift_moderation_router
from .main_menu import admin_menu_router
from .stats import admin_stats_router
from .mailing import admin_mailing_router
from .referrals import admin_referral_router
from .backups import admin_backup_router
from .adverts import admin_adverts_router
from .subscribes import admin_subscribes_router
from .withdrawal import withdrawal_admin_router
from .commands import admin_commands_router

def get_admin_routers():
    return [
        admin_menu_router,
        withdrawal_admin_router,
        admin_stats_router,
        admin_mailing_router,
        admin_referral_router,
        admin_backup_router,
        admin_adverts_router,
        admin_subscribes_router,
        admin_commands_router,
        gift_moderation_router
    ]