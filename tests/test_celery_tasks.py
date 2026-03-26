# tests/test_celery_tasks.py
"""Celery task 单元测试 — 直接调用函数，mock Redis lock 和 DB session"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.models.connector import Connector
from src.models.sync import SyncTask, SyncLog


@pytest.fixture
def mock_lock_success():
    """模拟 Redis 锁 — 获取成功"""
    lock = MagicMock()
    lock.acquire.return_value = True
    lock.release.return_value = None
    return lock


@pytest.fixture
def mock_lock_fail():
    """模拟 Redis 锁 — 获取失败（已被锁定）"""
    lock = MagicMock()
    lock.acquire.return_value = False
    return lock


@pytest.fixture
def connector_and_task(db_session):
    """创建测试用 Connector + SyncTask"""
    connector = Connector(
        name="测试连接器",
        connector_type="kingdee_erp",
        base_url="https://erp.test.com",
        auth_config={"test": True},
        enabled=True,
    )
    db_session.add(connector)
    db_session.flush()

    task = SyncTask(
        connector_id=connector.id,
        entity="order",
        direction="pull",
        cron_expression="*/30 * * * *",
        enabled=True,
    )
    db_session.add(task)
    db_session.flush()
    return connector, task


class TestRunSyncTaskLocking:
    """分布式锁相关测试"""

    def test_lock_conflict_skips(self, mocker, mock_lock_fail):
        """锁获取失败应跳过执行"""
        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_fail)

        from src.tasks.sync_tasks import run_sync_task
        result = run_sync_task(999)
        assert result["status"] == "skipped"
        assert result["reason"] == "already_running"

    def test_lock_acquired_and_released(self, db_session, mocker, mock_lock_success, connector_and_task):
        """成功执行后应释放锁"""
        _, task = connector_and_task
        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_success)
        mocker.patch("src.tasks.sync_tasks.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, 'close')

        # mock connector 的 connect/pull/disconnect
        mock_connector_instance = MagicMock()
        mock_connector_instance.pull.return_value = []
        mock_connector_class = MagicMock(return_value=mock_connector_instance)
        mocker.patch("src.tasks.sync_tasks.connector_registry.get", return_value=mock_connector_class)

        from src.tasks.sync_tasks import run_sync_task
        result = run_sync_task(task.id)

        mock_lock_success.release.assert_called_once()


class TestRunSyncTaskExecution:
    """任务执行逻辑测试"""

    def test_task_not_found(self, db_session, mocker, mock_lock_success):
        """task_id 不存在应跳过"""
        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_success)
        mocker.patch("src.tasks.sync_tasks.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, 'close')

        from src.tasks.sync_tasks import run_sync_task
        result = run_sync_task(99999)
        assert result["status"] == "skipped"
        assert result["reason"] == "not_found_or_disabled"

    def test_task_disabled(self, db_session, mocker, mock_lock_success, connector_and_task):
        """disabled task 应跳过"""
        _, task = connector_and_task
        task.enabled = False
        db_session.flush()

        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_success)
        mocker.patch("src.tasks.sync_tasks.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, 'close')

        from src.tasks.sync_tasks import run_sync_task
        result = run_sync_task(task.id)
        assert result["status"] == "skipped"
        assert result["reason"] == "not_found_or_disabled"

    def test_connector_disabled(self, db_session, mocker, mock_lock_success, connector_and_task):
        """connector disabled 应跳过"""
        connector, task = connector_and_task
        connector.enabled = False
        db_session.flush()

        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_success)
        mocker.patch("src.tasks.sync_tasks.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, 'close')

        from src.tasks.sync_tasks import run_sync_task
        result = run_sync_task(task.id)
        assert result["status"] == "skipped"
        assert result["reason"] == "connector_unavailable"

    def test_pull_success(self, db_session, mocker, mock_lock_success, connector_and_task):
        """成功的 pull 应创建 SyncLog、更新 last_sync_at"""
        connector, task = connector_and_task
        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_success)
        mocker.patch("src.tasks.sync_tasks.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, 'close')

        # mock connector
        mock_connector_instance = MagicMock()
        mock_connector_instance.pull.return_value = [
            {"FBillNo": "ORD001", "amount": 100},
        ]
        mock_connector_class = MagicMock(return_value=mock_connector_instance)
        mocker.patch("src.tasks.sync_tasks.connector_registry.get", return_value=mock_connector_class)

        # mock SyncExecutor.execute_pull
        mocker.patch(
            "src.tasks.sync_tasks.SyncExecutor.execute_pull",
            return_value={"status": "success", "total_records": 1, "success_count": 1, "failure_count": 0, "errors": []},
        )

        from src.tasks.sync_tasks import run_sync_task
        result = run_sync_task(task.id)

        assert result["status"] == "success"

        # 验证 SyncLog 已创建
        logs = db_session.query(SyncLog).filter_by(sync_task_id=task.id).all()
        assert len(logs) == 1
        assert logs[0].status == "success"

        # 验证 last_sync_at 已更新
        db_session.refresh(task)
        assert task.last_sync_at is not None

    def test_pull_connector_error_recorded(self, db_session, mocker, mock_lock_success, connector_and_task):
        """ConnectorError 应记录失败日志"""
        from src.connectors.base import ConnectorError

        connector, task = connector_and_task
        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_success)
        mocker.patch("src.tasks.sync_tasks.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, 'close')

        # mock connector that raises
        mock_connector_instance = MagicMock()
        mock_connector_class = MagicMock(return_value=mock_connector_instance)
        mocker.patch("src.tasks.sync_tasks.connector_registry.get", return_value=mock_connector_class)

        mocker.patch(
            "src.tasks.sync_tasks.SyncExecutor.execute_pull",
            side_effect=ConnectorError("API timeout"),
        )

        # 由于 autoretry_for 在直接调用时不生效，ConnectorError 会抛出
        from src.tasks.sync_tasks import run_sync_task
        with pytest.raises(ConnectorError):
            run_sync_task(task.id)

        # 验证 SyncLog 状态为 failed
        logs = db_session.query(SyncLog).filter_by(sync_task_id=task.id).all()
        assert len(logs) == 1
        assert logs[0].status == "failed"

    def test_push_direction_skipped(self, db_session, mocker, mock_lock_success, connector_and_task):
        """push 方向任务应跳过"""
        connector, task = connector_and_task
        task.direction = "push"
        db_session.flush()

        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_success)
        mocker.patch("src.tasks.sync_tasks.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, 'close')

        from src.tasks.sync_tasks import run_sync_task
        result = run_sync_task(task.id)
        assert result["status"] == "skipped"

    def test_generic_exception_handled(self, db_session, mocker, mock_lock_success, connector_and_task):
        """非 ConnectorError 异常应记录失败但不重试"""
        connector, task = connector_and_task
        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_success)
        mocker.patch("src.tasks.sync_tasks.get_session_local", return_value=lambda: db_session)
        mocker.patch.object(db_session, 'close')

        mock_connector_instance = MagicMock()
        mock_connector_class = MagicMock(return_value=mock_connector_instance)
        mocker.patch("src.tasks.sync_tasks.connector_registry.get", return_value=mock_connector_class)
        mocker.patch(
            "src.tasks.sync_tasks.SyncExecutor.execute_pull",
            side_effect=RuntimeError("Unexpected error"),
        )

        from src.tasks.sync_tasks import run_sync_task
        result = run_sync_task(task.id)

        assert result["status"] == "failed"
        assert "Unexpected error" in result["error"]

        # 验证 SyncLog 状态为 failed
        logs = db_session.query(SyncLog).filter_by(sync_task_id=task.id).all()
        assert len(logs) == 1
        assert logs[0].status == "failed"
