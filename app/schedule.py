import config
import json

from datetime import timedelta

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import redis_pool
from app.utils.misc_function import get_time_now
from app.utils.scheduler_instance import scheduler
from app.utils.utils import daily_backup, check_subs, send_push_to_inactive_users, send_channel_posts


async def scheduler_start():
    try:

        scheduler.add_job(
            daily_backup,
            CronTrigger(hour=0, minute=5), 
            id='daily_backup',
            replace_existing=True,
            max_instances=1 
        )

        scheduler.add_job(
            check_subs,
            IntervalTrigger(minutes=5, jitter=30),
            id='subscription_check',
            replace_existing=True
        )

        scheduler.add_job(
            send_push_to_inactive_users,
            CronTrigger(hour=12, minute=30),
            id='inactive_users_push',
            replace_existing=True
        )
        scheduler.add_job(
            send_channel_posts,
            CronTrigger(hour='12,20', minute=0),
            id='channel_posts',
            replace_existing=True
        )

        scheduler.start()
        print("Scheduler started successfully with Redis backend")
        
    except Exception as e:
        print(f"Failed to start scheduler: {str(e)}")
        raise