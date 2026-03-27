# src/core/celery_app.py
"""Celery 应用实例"""

from celery import Celery
from src.core.config import get_settings

settings = get_settings()

celery_app = Celery("data_platform")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL or settings.REDIS_URL,
    result_backend=settings.CELERY_RESULT_BACKEND or settings.REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_hijack_root_logger=False,
)
celery_app.conf.update(include=["src.tasks.sync_tasks", "src.tasks.flow_tasks"])
