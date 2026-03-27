# tests/test_scheduler.py
"""DatabaseScheduler 单元测试"""

import pytest
from unittest.mock import MagicMock, patch

from src.models.connector import Connector
from src.models.sync import SyncTask
from src.tasks.scheduler import BUILTIN_PERIODIC_TASKS

BUILTIN_COUNT = len(BUILTIN_PERIODIC_TASKS)


@pytest.fixture
def connector_in_db(db_session):
    c = Connector(
        name="调度测试连接器",
        connector_type="kingdee_erp",
        base_url="https://erp.test.com",
        auth_config={"test": True},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


@pytest.fixture
def mock_celery_app():
    app = MagicMock()
    app.conf = MagicMock()
    return app


class TestDatabaseScheduler:
    def test_loads_enabled_tasks(self, db_session, connector_in_db, mock_celery_app, mocker):
        """应只加载 enabled=True 且有 cron_expression 的任务"""
        # 创建 3 个任务：2 个 enabled + cron，1 个 disabled
        for i in range(2):
            db_session.add(
                SyncTask(
                    connector_id=connector_in_db.id,
                    entity=f"entity_{i}",
                    direction="pull",
                    cron_expression="*/30 * * * *",
                    enabled=True,
                )
            )
        db_session.add(
            SyncTask(
                connector_id=connector_in_db.id,
                entity="disabled_entity",
                direction="pull",
                cron_expression="0 * * * *",
                enabled=False,
            )
        )
        db_session.flush()

        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, "close")

        from src.tasks.scheduler import DatabaseScheduler

        scheduler = DatabaseScheduler(app=mock_celery_app)

        assert len(scheduler.schedule) == 2 + BUILTIN_COUNT

    def test_skips_null_cron(self, db_session, connector_in_db, mock_celery_app, mocker):
        """cron_expression 为 None 的任务不应加载"""
        db_session.add(
            SyncTask(
                connector_id=connector_in_db.id,
                entity="no_cron",
                direction="pull",
                cron_expression=None,
                enabled=True,
            )
        )
        db_session.flush()

        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, "close")

        from src.tasks.scheduler import DatabaseScheduler

        scheduler = DatabaseScheduler(app=mock_celery_app)

        assert len(scheduler.schedule) == BUILTIN_COUNT

    def test_skips_invalid_cron(self, db_session, connector_in_db, mock_celery_app, mocker):
        """非法 cron 表达式（非 5 段）应跳过"""
        db_session.add(
            SyncTask(
                connector_id=connector_in_db.id,
                entity="bad_cron",
                direction="pull",
                cron_expression="invalid",
                enabled=True,
            )
        )
        db_session.flush()

        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, "close")

        from src.tasks.scheduler import DatabaseScheduler

        scheduler = DatabaseScheduler(app=mock_celery_app)

        assert len(scheduler.schedule) == BUILTIN_COUNT

    def test_refresh_picks_up_new_task(self, db_session, connector_in_db, mock_celery_app, mocker):
        """刷新后应发现新增的任务"""
        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, "close")

        from src.tasks.scheduler import DatabaseScheduler

        scheduler = DatabaseScheduler(app=mock_celery_app)
        assert len(scheduler.schedule) == BUILTIN_COUNT

        # 新增一个任务
        db_session.add(
            SyncTask(
                connector_id=connector_in_db.id,
                entity="new_entity",
                direction="pull",
                cron_expression="0 * * * *",
                enabled=True,
            )
        )
        db_session.flush()

        # 强制刷新
        scheduler._last_sync = 0
        schedule = scheduler.schedule  # 触发刷新
        assert len(schedule) == 1 + BUILTIN_COUNT

    def test_refresh_removes_disabled_task(
        self, db_session, connector_in_db, mock_celery_app, mocker
    ):
        """禁用任务后刷新应从调度表中移除"""
        task = SyncTask(
            connector_id=connector_in_db.id,
            entity="to_disable",
            direction="pull",
            cron_expression="0 * * * *",
            enabled=True,
        )
        db_session.add(task)
        db_session.flush()

        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, "close")

        from src.tasks.scheduler import DatabaseScheduler

        scheduler = DatabaseScheduler(app=mock_celery_app)
        assert len(scheduler.schedule) == 1 + BUILTIN_COUNT

        # 禁用
        task.enabled = False
        db_session.flush()

        scheduler._last_sync = 0
        schedule = scheduler.schedule
        assert len(schedule) == BUILTIN_COUNT

    def test_empty_table(self, db_session, mock_celery_app, mocker):
        """空表应返回空调度"""
        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, "close")

        from src.tasks.scheduler import DatabaseScheduler

        scheduler = DatabaseScheduler(app=mock_celery_app)
        assert len(scheduler.schedule) == BUILTIN_COUNT
