from apscheduler.schedulers.background import BackgroundScheduler
from ..config import settings
from .reminder_service import trigger_overdue_reminders
from ..repositories.users import get_all_users
from ..db import SessionLocal
import logging

scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)

def _parse_time(t: str) -> tuple[int, int]:
    h, m = map(int, t.split(":"))
    return h, m

def _run_daily_reminders() -> None:
    """Job executed daily by scheduler."""
    db = SessionLocal()
    try:
        users = get_all_users(db)
        for user in users:
            try:
                result = trigger_overdue_reminders(db, user.id)
                logger.info("Scheduler completed for user %s: %s", user.id, result)
            except Exception as e:
                logger.exception("Scheduler job failed for user %s", user.id)
    finally:
        db.close()

def start_scheduler() -> None:
    hour, minute = _parse_time(settings.scheduler_time)
    scheduler.add_job(_run_daily_reminders, "cron", hour=hour, minute=minute)
    scheduler.start()
    logger.info("Started scheduler with job at %s UTC", settings.scheduler_time)

def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
