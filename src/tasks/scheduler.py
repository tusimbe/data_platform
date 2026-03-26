# src/tasks/scheduler.py
"""自定义 Celery Beat Scheduler — 从 SyncTask 表动态加载调度配置"""
import logging
import time

from celery.beat import Scheduler, ScheduleEntry
from celery.schedules import crontab

from src.core.config import get_settings
from src.core.database import get_session_local
from src.models.sync import SyncTask

logger = logging.getLogger(__name__)
settings = get_settings()


class DatabaseScheduler(Scheduler):
    """从 SyncTask 表动态加载调度的 Celery Beat Scheduler。

    每 sync_every 秒从数据库刷新一次调度表，自动发现
    新增/修改/删除/禁用的任务。
    """

    def __init__(self, *args, **kwargs):
        self._schedule = {}
        self._last_sync = 0.0
        self.sync_every = settings.SCHEDULER_SYNC_INTERVAL
        super().__init__(*args, **kwargs)

    def setup_schedule(self):
        """Beat 启动时从 DB 加载全部活跃任务"""
        self._sync_from_db()

    def _sync_from_db(self):
        """查询 SyncTask 表，重建内存调度表"""
        SessionLocal = get_session_local()
        session = SessionLocal()
        try:
            tasks = (
                session.query(SyncTask)
                .filter(
                    SyncTask.enabled.is_(True),
                    SyncTask.cron_expression.isnot(None),
                )
                .all()
            )

            new_schedule = {}
            for task in tasks:
                entry_name = f"sync_task_{task.id}"
                parts = task.cron_expression.split()
                if len(parts) != 5:
                    logger.warning(
                        f"Skipping task {task.id}: invalid cron '{task.cron_expression}'"
                    )
                    continue

                schedule = crontab(
                    minute=parts[0],
                    hour=parts[1],
                    day_of_month=parts[2],
                    month_of_year=parts[3],
                    day_of_week=parts[4],
                )
                entry = ScheduleEntry(
                    name=entry_name,
                    task="sync.run_sync_task",
                    schedule=schedule,
                    args=(task.id,),
                    app=self.app,
                )
                # 保留已有 entry 的运行状态（last_run_at 等）
                if entry_name in self._schedule:
                    entry.last_run_at = self._schedule[entry_name].last_run_at

                new_schedule[entry_name] = entry

            self._schedule = new_schedule
            logger.debug(f"Scheduler synced: {len(new_schedule)} active tasks")
        except Exception as e:
            logger.exception(f"Failed to sync schedule from DB: {e}")
        finally:
            self._last_sync = time.time()
            session.close()

    @property
    def schedule(self):
        """返回调度表，定期刷新"""
        if time.time() - self._last_sync > self.sync_every:
            self._sync_from_db()
        return self._schedule

    @schedule.setter
    def schedule(self, value):
        """允许父类设置 schedule（初始化时需要）"""
        self._schedule = value
