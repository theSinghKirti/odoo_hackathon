from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "subscription_manager",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.billing_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "daily-automated-billing-sweep": {
            "task": "app.workers.billing_tasks.run_daily_billing_sweep",
            "schedule": crontab(hour=0, minute=0),  # Daily at 00:00 UTC per business rules
        },
    },
)

