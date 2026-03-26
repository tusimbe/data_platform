# P1 Sub-project 6: 调度与监控 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将同步任务从同步执行改为 Celery 异步调度，实现定时调度、分布式锁防并发、健康检查增强。

**Architecture:** 自定义 DatabaseScheduler 从 SyncTask 表轮询调度配置，Celery Worker 执行 run_sync_task，Redis 提供 broker + 分布式锁。手动触发改为异步入队返回 202。

**Tech Stack:** Celery 5.4+, Redis 7, croniter, pytest-mock

**Spec:** `docs/superpowers/specs/2026-03-26-p1-scheduling-monitoring-design.md`

---

## 文件结构

### 新建文件
| 文件 | 职责 |
|------|------|
| `src/core/celery_app.py` | Celery 应用实例 + 配置 |
| `src/tasks/__init__.py` | 包标识（空文件） |
| `src/tasks/sync_tasks.py` | `run_sync_task` Celery task + Redis 分布式锁 + `_entity_to_table` |
| `src/tasks/scheduler.py` | DatabaseScheduler（从 SyncTask 表加载调度） |
| `tests/test_celery_tasks.py` | run_sync_task 单元测试 |
| `tests/test_scheduler.py` | DatabaseScheduler 单元测试 |
| `tests/test_compute_next_run.py` | `_compute_next_run` 纯函数测试 |

### 修改文件
| 文件 | 变更 |
|------|------|
| `pyproject.toml:6-17` | 添加 `croniter>=2.0.0` 依赖；dev 依赖添加 `pytest-mock>=3.0.0` |
| `src/core/config.py:4-26` | 新增 6 个 Celery/调度/锁/重试配置项 |
| `src/core/database.py` | 导出 `SessionLocal` 供 Celery task/scheduler 使用 |
| `src/services/sync_task_service.py:68-124` | `trigger_sync` 改为入队 Celery task |
| `src/services/sync_task_service.py:185-191` | `_compute_next_run` 用 croniter 实现 |
| `src/api/routes/sync_tasks.py:63-70` | trigger 路由改为 202，移除 `session.commit()` |
| `src/api/schemas/sync.py` | 新增 `SyncTaskTriggerResponse` schema |
| `src/api/routes/health.py:31-35` | 替换 Redis/Celery stub 为真实检查 |
| `docker-compose.yml` | 新增 celery-worker、celery-beat 服务 |
| `tests/test_api_sync_tasks.py` | trigger 测试改为断言 202 |
| `tests/test_api_health.py:49-52` | 更新 Redis/Celery 健康检查测试 |

---

### Task 1: 依赖与配置基础

**Files:**
- Modify: `pyproject.toml:6-17,19-25`
- Modify: `src/core/config.py:4-26`
- Modify: `src/core/database.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 添加 croniter 和 pytest-mock 依赖**

`pyproject.toml` — 在 `dependencies` 中添加 `croniter`，在 `dev` 中添加 `pytest-mock`：

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "psycopg2-binary>=2.9.0",
    "alembic>=1.13.0",
    "celery[redis]>=5.4.0",
    "redis>=5.0.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.27.0",
    "cryptography>=42.0.0",
    "croniter>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.0.0",
    "httpx>=0.27.0",
    "ruff>=0.5.0",
]
```

- [ ] **Step 2: 安装新依赖**

Run: `pip install -e ".[dev]"`
Expected: Successfully installed croniter, pytest-mock

- [ ] **Step 3: 扩展 Settings 配置**

`src/core/config.py` — 在 `Settings` 类中添加 Celery/调度/锁/重试配置：

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，支持环境变量和 .env 文件"""

    APP_NAME: str = "数据中台"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # 数据库
    DATABASE_URL: str
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str

    # API
    API_V1_PREFIX: str = "/api/v1"
    API_KEY: str = ""

    # 安全
    ENCRYPTION_KEY: str = ""

    # Celery
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # 调度器
    SCHEDULER_SYNC_INTERVAL: int = 15

    # 分布式锁
    SYNC_LOCK_TIMEOUT: int = 3600

    # 任务重试
    SYNC_TASK_MAX_RETRIES: int = 3
    SYNC_TASK_RETRY_BACKOFF: int = 60

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: 导出 SessionLocal**

`src/core/database.py` — 添加 `get_session_local()` 函数，供 Celery task 和 scheduler 获取 SessionLocal（不依赖 FastAPI 的 `get_session` 生成器）：

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

_engine = None
_SessionLocal = None


def init_db(database_url: str, echo: bool = False):
    global _engine, _SessionLocal
    _engine = create_engine(database_url, echo=echo)
    _SessionLocal = sessionmaker(bind=_engine)


def get_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_session_local():
    """返回 SessionLocal 工厂，供非 FastAPI 环境使用（Celery task/scheduler）。
    如果 DB 未初始化，自动初始化。"""
    global _engine, _SessionLocal
    if _SessionLocal is None:
        from src.core.config import get_settings
        settings = get_settings()
        init_db(settings.DATABASE_URL, settings.DATABASE_ECHO)
    return _SessionLocal
```

- [ ] **Step 5: 运行现有测试确认无回归**

Run: `pytest tests/ -v`
Expected: All 158 tests PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/core/config.py src/core/database.py
git commit -m "feat: 添加 Celery 配置项、croniter 依赖和 SessionLocal 导出"
```

---

### Task 2: Celery 应用实例

**Files:**
- Create: `src/core/celery_app.py`
- Test: 无独立测试（在后续 task 测试中覆盖）

- [ ] **Step 1: 创建 Celery 应用实例**

`src/core/celery_app.py`:

```python
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
celery_app.autodiscover_tasks(["src.tasks"])
```

- [ ] **Step 2: 创建 tasks 包**

创建 `src/tasks/__init__.py`（空文件）。

- [ ] **Step 3: 运行现有测试确认无回归**

Run: `pytest tests/ -v`
Expected: All 158 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/core/celery_app.py src/tasks/__init__.py
git commit -m "feat: 创建 Celery 应用实例和 tasks 包"
```

---

### Task 3: _compute_next_run 实现 + 测试

**Files:**
- Modify: `src/services/sync_task_service.py:1-6,185-191`
- Create: `tests/test_compute_next_run.py`

- [ ] **Step 1: 编写 _compute_next_run 失败测试**

`tests/test_compute_next_run.py`:

```python
# tests/test_compute_next_run.py
"""_compute_next_run 纯函数测试"""
from datetime import datetime, timezone
from unittest.mock import patch


def test_compute_next_run_with_valid_cron():
    """有效 cron 表达式应返回未来的 datetime"""
    from src.services.sync_task_service import _compute_next_run

    result = _compute_next_run("*/30 * * * *")
    assert result is not None
    assert isinstance(result, datetime)
    assert result > datetime.now(timezone.utc)


def test_compute_next_run_none_cron():
    """cron_expression 为 None 应返回 None"""
    from src.services.sync_task_service import _compute_next_run

    result = _compute_next_run(None)
    assert result is None


def test_compute_next_run_empty_cron():
    """空字符串 cron_expression 应返回 None"""
    from src.services.sync_task_service import _compute_next_run

    result = _compute_next_run("")
    assert result is None


def test_compute_next_run_invalid_cron():
    """非法 cron 表达式应返回 None（不抛异常）"""
    from src.services.sync_task_service import _compute_next_run

    result = _compute_next_run("invalid cron expression")
    assert result is None
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_compute_next_run.py -v`
Expected: `test_compute_next_run_with_valid_cron` FAIL（当前 stub 返回 None）

- [ ] **Step 3: 实现 _compute_next_run**

修改 `src/services/sync_task_service.py`：

顶部添加导入：
```python
from croniter import croniter
```

替换 `_compute_next_run` 函数（第 185-191 行）：

```python
def _compute_next_run(cron_expression: str | None) -> datetime | None:
    """从 cron 表达式计算下次运行时间。无 cron 或非法表达式返回 None。"""
    if not cron_expression:
        return None
    try:
        cron = croniter(cron_expression, datetime.now(timezone.utc))
        return cron.get_next(datetime)
    except (ValueError, KeyError):
        return None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_compute_next_run.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: 运行全量测试确认无回归**

Run: `pytest tests/ -v`
Expected: All 162 tests PASS (158 + 4 new)

- [ ] **Step 6: Commit**

```bash
git add src/services/sync_task_service.py tests/test_compute_next_run.py
git commit -m "feat: 用 croniter 实现 _compute_next_run 计算下次调度时间"
```

---

### Task 4: run_sync_task Celery Task

**Files:**
- Create: `src/tasks/sync_tasks.py`
- Create: `tests/test_celery_tasks.py`

- [ ] **Step 1: 编写 run_sync_task 测试**

`tests/test_celery_tasks.py`:

```python
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

        from src.tasks.sync_tasks import run_sync_task
        result = run_sync_task(task.id)
        assert result["status"] == "skipped"
        assert result["reason"] == "connector_unavailable"

    def test_pull_success(self, db_session, mocker, mock_lock_success, connector_and_task):
        """成功的 pull 应创建 SyncLog、更新 last_sync_at"""
        connector, task = connector_and_task
        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_success)
        mocker.patch("src.tasks.sync_tasks.get_session_local", return_value=lambda: db_session)

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

        from src.tasks.sync_tasks import run_sync_task
        result = run_sync_task(task.id)
        assert result["status"] == "skipped"

    def test_generic_exception_handled(self, db_session, mocker, mock_lock_success, connector_and_task):
        """非 ConnectorError 异常应记录失败但不重试"""
        connector, task = connector_and_task
        mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock_success)
        mocker.patch("src.tasks.sync_tasks.get_session_local", return_value=lambda: db_session)

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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_celery_tasks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.tasks.sync_tasks'`

- [ ] **Step 3: 实现 run_sync_task**

`src/tasks/sync_tasks.py`:

```python
# src/tasks/sync_tasks.py
"""Celery 同步任务定义"""
import json
import logging
from datetime import datetime, timezone

import redis

from src.core.celery_app import celery_app
from src.core.config import get_settings
from src.core.database import get_session_local
from src.core.security import decrypt_value
from src.connectors.base import connector_registry, ConnectorError
from src.models.connector import Connector
from src.models.sync import SyncTask, SyncLog
from src.services.sync_service import SyncExecutor

logger = logging.getLogger(__name__)
settings = get_settings()
redis_client = redis.from_url(settings.REDIS_URL)


def _entity_to_table(entity: str) -> str:
    """将实体名映射到统一表名"""
    mapping = {
        "customer": "unified_customers",
        "order": "unified_orders",
        "product": "unified_products",
        "inventory": "unified_inventory",
        "project": "unified_projects",
        "contact": "unified_contacts",
        "sales_order": "unified_orders",
        "material": "unified_products",
    }
    return mapping.get(entity, f"unified_{entity}")


@celery_app.task(
    name="sync.run_sync_task",
    autoretry_for=(ConnectorError,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=settings.SYNC_TASK_MAX_RETRIES,
    acks_late=True,
)
def run_sync_task(task_id: int):
    """执行单个 SyncTask 的同步"""
    lock = redis_client.lock(
        name=f"sync_lock:{task_id}",
        timeout=settings.SYNC_LOCK_TIMEOUT,
        blocking=False,
    )

    if not lock.acquire(blocking=False):
        logger.info(f"Task {task_id} already running, skipping")
        return {"status": "skipped", "reason": "already_running"}

    SessionLocal = get_session_local()
    session = SessionLocal()
    sync_log = None
    try:
        # 1. 加载任务和连接器
        task = session.query(SyncTask).filter_by(id=task_id).first()
        if not task or not task.enabled:
            logger.warning(f"Task {task_id} not found or disabled")
            return {"status": "skipped", "reason": "not_found_or_disabled"}

        connector_model = session.query(Connector).filter_by(id=task.connector_id).first()
        if not connector_model or not connector_model.enabled:
            logger.warning(f"Connector for task {task_id} not found or disabled")
            return {"status": "skipped", "reason": "connector_unavailable"}

        # 2. 创建 SyncLog
        sync_log = SyncLog(
            sync_task_id=task.id,
            connector_id=connector_model.id,
            entity=task.entity,
            direction=task.direction,
            status="running",
        )
        session.add(sync_log)
        session.flush()

        # 3. push 方向暂不支持
        if task.direction != "pull":
            sync_log.status = "skipped"
            sync_log.finished_at = datetime.now(timezone.utc)
            session.commit()
            return {"status": "skipped", "reason": "push_not_supported", "task_id": task_id}

        # 4. 实例化连接器
        connector_class = connector_registry.get(connector_model.connector_type)
        auth_config = connector_model.auth_config
        if isinstance(auth_config, dict) and "_encrypted" in auth_config:
            decrypted = decrypt_value(auth_config["_encrypted"], settings.ENCRYPTION_KEY)
            auth_config = json.loads(decrypted)

        config = {
            "base_url": connector_model.base_url,
            "auth_config": auth_config,
        }
        connector = connector_class(config)

        # 5. 执行同步
        try:
            connector.connect()
            executor = SyncExecutor()
            target_table = _entity_to_table(task.entity)
            result = executor.execute_pull(
                connector=connector,
                connector_id=connector_model.id,
                entity=task.entity,
                target_table=target_table,
                mappings=[],
                session=session,
                since=task.last_sync_at,
            )

            # 更新状态
            sync_log.status = "success"
            sync_log.total_records = result.get("total_records", 0)
            sync_log.success_count = result.get("success_count", 0)
            sync_log.finished_at = datetime.now(timezone.utc)
            task.last_sync_at = datetime.now(timezone.utc)
        finally:
            try:
                connector.disconnect()
            except Exception:
                pass

        session.commit()
        logger.info(f"Task {task_id} completed: {sync_log.status}")
        return {"status": sync_log.status, "task_id": task_id}

    except ConnectorError:
        # 让 Celery autoretry 处理
        if sync_log:
            sync_log.status = "failed"
            sync_log.finished_at = datetime.now(timezone.utc)
            session.commit()
        raise
    except Exception as e:
        logger.exception(f"Task {task_id} failed: {e}")
        if sync_log:
            sync_log.status = "failed"
            sync_log.error_details = {"error": str(e)}
            sync_log.finished_at = datetime.now(timezone.utc)
        session.commit()
        return {"status": "failed", "task_id": task_id, "error": str(e)}
    finally:
        session.close()
        try:
            lock.release()
        except redis.exceptions.LockNotOwnedError:
            pass  # 锁已过期
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_celery_tasks.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: 运行全量测试确认无回归**

Run: `pytest tests/ -v`
Expected: All 171 tests PASS (162 + 9 new)

- [ ] **Step 6: Commit**

```bash
git add src/tasks/sync_tasks.py tests/test_celery_tasks.py
git commit -m "feat: 实现 run_sync_task Celery task 及 Redis 分布式锁"
```

---

### Task 5: DatabaseScheduler

**Files:**
- Create: `src/tasks/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: 编写 Scheduler 测试**

`tests/test_scheduler.py`:

```python
# tests/test_scheduler.py
"""DatabaseScheduler 单元测试"""
import pytest
from unittest.mock import MagicMock, patch

from src.models.connector import Connector
from src.models.sync import SyncTask


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
            db_session.add(SyncTask(
                connector_id=connector_in_db.id,
                entity=f"entity_{i}",
                direction="pull",
                cron_expression="*/30 * * * *",
                enabled=True,
            ))
        db_session.add(SyncTask(
            connector_id=connector_in_db.id,
            entity="disabled_entity",
            direction="pull",
            cron_expression="0 * * * *",
            enabled=False,
        ))
        db_session.flush()

        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)

        from src.tasks.scheduler import DatabaseScheduler
        scheduler = DatabaseScheduler(app=mock_celery_app)

        assert len(scheduler.schedule) == 2

    def test_skips_null_cron(self, db_session, connector_in_db, mock_celery_app, mocker):
        """cron_expression 为 None 的任务不应加载"""
        db_session.add(SyncTask(
            connector_id=connector_in_db.id,
            entity="no_cron",
            direction="pull",
            cron_expression=None,
            enabled=True,
        ))
        db_session.flush()

        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)

        from src.tasks.scheduler import DatabaseScheduler
        scheduler = DatabaseScheduler(app=mock_celery_app)

        assert len(scheduler.schedule) == 0

    def test_skips_invalid_cron(self, db_session, connector_in_db, mock_celery_app, mocker):
        """非法 cron 表达式（非 5 段）应跳过"""
        db_session.add(SyncTask(
            connector_id=connector_in_db.id,
            entity="bad_cron",
            direction="pull",
            cron_expression="invalid",
            enabled=True,
        ))
        db_session.flush()

        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)

        from src.tasks.scheduler import DatabaseScheduler
        scheduler = DatabaseScheduler(app=mock_celery_app)

        assert len(scheduler.schedule) == 0

    def test_refresh_picks_up_new_task(self, db_session, connector_in_db, mock_celery_app, mocker):
        """刷新后应发现新增的任务"""
        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)

        from src.tasks.scheduler import DatabaseScheduler
        scheduler = DatabaseScheduler(app=mock_celery_app)
        assert len(scheduler.schedule) == 0

        # 新增一个任务
        db_session.add(SyncTask(
            connector_id=connector_in_db.id,
            entity="new_entity",
            direction="pull",
            cron_expression="0 * * * *",
            enabled=True,
        ))
        db_session.flush()

        # 强制刷新
        scheduler._last_sync = 0
        schedule = scheduler.schedule  # 触发刷新
        assert len(schedule) == 1

    def test_refresh_removes_disabled_task(self, db_session, connector_in_db, mock_celery_app, mocker):
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

        from src.tasks.scheduler import DatabaseScheduler
        scheduler = DatabaseScheduler(app=mock_celery_app)
        assert len(scheduler.schedule) == 1

        # 禁用
        task.enabled = False
        db_session.flush()

        scheduler._last_sync = 0
        schedule = scheduler.schedule
        assert len(schedule) == 0

    def test_empty_table(self, db_session, mock_celery_app, mocker):
        """空表应返回空调度"""
        mocker.patch("src.tasks.scheduler.get_session_local", return_value=lambda: db_session)

        from src.tasks.scheduler import DatabaseScheduler
        scheduler = DatabaseScheduler(app=mock_celery_app)
        assert len(scheduler.schedule) == 0
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_scheduler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.tasks.scheduler'`

- [ ] **Step 3: 实现 DatabaseScheduler**

`src/tasks/scheduler.py`:

```python
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
                    SyncTask.enabled == True,
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
            self._last_sync = time.time()
            logger.debug(f"Scheduler synced: {len(new_schedule)} active tasks")
        except Exception as e:
            logger.exception(f"Failed to sync schedule from DB: {e}")
        finally:
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_scheduler.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: 运行全量测试确认无回归**

Run: `pytest tests/ -v`
Expected: All 177 tests PASS (171 + 6 new)

- [ ] **Step 6: Commit**

```bash
git add src/tasks/scheduler.py tests/test_scheduler.py
git commit -m "feat: 实现 DatabaseScheduler 从 SyncTask 表动态加载调度"
```

---

### Task 6: API 层变更（trigger 202 + Schema）

**Files:**
- Modify: `src/api/schemas/sync.py`
- Modify: `src/services/sync_task_service.py:1-16,68-124`
- Modify: `src/api/routes/sync_tasks.py:63-70`
- Modify: `tests/test_api_sync_tasks.py`

- [ ] **Step 1: 编写 trigger 202 测试**

在 `tests/test_api_sync_tasks.py` 末尾追加测试类（替换现有 trigger 测试如有）：

```python
class TestTriggerSync:
    def test_trigger_returns_202(self, client, api_headers, sample_task_data, mocker):
        """手动触发应返回 202 Accepted"""
        create_resp = client.post("/api/v1/sync-tasks", json=sample_task_data, headers=api_headers)
        tid = create_resp.json()["id"]

        # mock Celery delay
        mock_result = MagicMock()
        mock_result.id = "fake-celery-task-id"
        mocker.patch(
            "src.services.sync_task_service.run_sync_task.delay",
            return_value=mock_result,
        )

        resp = client.post(f"/api/v1/sync-tasks/{tid}/trigger", headers=api_headers)
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["task_id"] == tid
        assert data["celery_task_id"] == "fake-celery-task-id"

    def test_trigger_disabled_task(self, client, api_headers, sample_task_data):
        """触发 disabled 任务应返回 400"""
        create_resp = client.post("/api/v1/sync-tasks", json=sample_task_data, headers=api_headers)
        tid = create_resp.json()["id"]
        # disable
        client.put(f"/api/v1/sync-tasks/{tid}", json={"enabled": False}, headers=api_headers)

        resp = client.post(f"/api/v1/sync-tasks/{tid}/trigger", headers=api_headers)
        assert resp.status_code == 400

    def test_trigger_not_found(self, client, api_headers):
        """触发不存在的任务应返回 404"""
        resp = client.post("/api/v1/sync-tasks/99999/trigger", headers=api_headers)
        assert resp.status_code == 404
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_api_sync_tasks.py::TestTriggerSync -v`
Expected: FAIL — 当前 trigger 返回 200（不是 202）

- [ ] **Step 3: 新增 SyncTaskTriggerResponse schema**

在 `src/api/schemas/sync.py` 末尾添加：

```python
class SyncTaskTriggerResponse(BaseModel):
    status: str
    task_id: int
    celery_task_id: str
    message: str
```

- [ ] **Step 4: 重构 trigger_sync service**

修改 `src/services/sync_task_service.py`：

替换 `trigger_sync` 函数（第 68-124 行）：

```python
def trigger_sync(session: Session, task_id: int) -> dict:
    """手动触发同步：验证后入队 Celery task"""
    task = get_sync_task(session, task_id)
    if not task.enabled:
        raise HTTPException(status_code=400, detail="Sync task is disabled")

    connector = session.query(Connector).filter_by(id=task.connector_id).first()
    if not connector or not connector.enabled:
        raise HTTPException(status_code=400, detail="Associated connector not found or disabled")

    from src.tasks.sync_tasks import run_sync_task
    result = run_sync_task.delay(task_id)
    return {
        "status": "accepted",
        "task_id": task_id,
        "celery_task_id": result.id,
        "message": "Sync task has been queued",
    }
```

同时移除 `sync_task_service.py` 中不再需要的导入：`json`, `ConnectorError`, `get_settings`, `decrypt_value`, `SyncExecutor`。保留 `_entity_to_table`（仍被 `sync_task_to_response` 等使用）。

注意：`trigger_sync` 不再需要 `from datetime import datetime, timezone` 中的 `timezone`（但其他函数可能仍需要）。只移除确实不再使用的导入。

- [ ] **Step 5: 修改路由**

修改 `src/api/routes/sync_tasks.py` 第 63-70 行：

```python
@router.post("/sync-tasks/{task_id}/trigger", status_code=202)
def trigger_sync(
    task_id: int,
    session: Session = Depends(get_db),
):
    return sync_task_service.trigger_sync(session, task_id)
```

注意：移除了原来的 `session.commit()`，因为 `trigger_sync` 不再写 DB。

- [ ] **Step 6: 运行测试验证通过**

Run: `pytest tests/test_api_sync_tasks.py -v`
Expected: All tests PASS（包括新的 TestTriggerSync）

- [ ] **Step 7: 运行全量测试确认无回归**

Run: `pytest tests/ -v`
Expected: All ~180 tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/api/schemas/sync.py src/services/sync_task_service.py src/api/routes/sync_tasks.py tests/test_api_sync_tasks.py
git commit -m "feat: 手动触发改为 Celery 异步入队，返回 202 Accepted"
```

---

### Task 7: 健康检查增强

**Files:**
- Modify: `src/api/routes/health.py`
- Modify: `tests/test_api_health.py`

- [ ] **Step 1: 编写健康检查测试**

重写 `tests/test_api_health.py`：

```python
# tests/test_api_health.py
"""增强版健康检查 API 测试"""
from unittest.mock import MagicMock


def test_root(client):
    """根路径应返回应用信息"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "数据中台"


def test_health_returns_status(client, mocker):
    """健康检查应返回 overall status"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_health_has_components(client, mocker):
    """健康检查应包含所有组件状态"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    data = resp.json()
    assert "database" in data["components"]
    assert "redis" in data["components"]
    assert "celery" in data["components"]


def test_health_database_latency(client, mocker):
    """数据库健康检查应返回延迟"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    db = resp.json()["components"]["database"]
    assert db["status"] == "healthy"
    assert "latency_ms" in db


def test_health_no_auth_required(client, mocker):
    """健康检查端点不需要认证"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_health_has_version(client, mocker):
    """健康检查应返回版本号"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    assert resp.json()["version"] == "0.1.0"


def test_health_redis_healthy(client, mocker):
    """Redis healthy 时应在组件中反映"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 2.5})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    redis_status = resp.json()["components"]["redis"]
    assert redis_status["status"] == "healthy"
    assert redis_status["latency_ms"] == 2.5


def test_health_redis_down_degraded(client, mocker):
    """Redis 不可用时 overall 应为 degraded"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "unhealthy", "error": "Connection refused"})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    assert resp.json()["status"] == "degraded"


def test_health_celery_down_degraded(client, mocker):
    """Celery 不可用时 overall 应为 degraded"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "unhealthy", "error": "No workers"})
    resp = client.get("/api/v1/health")
    assert resp.json()["status"] == "degraded"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_api_health.py -v`
Expected: FAIL — `_check_redis` 和 `_check_celery` 函数不存在

- [ ] **Step 3: 实现健康检查增强**

重写 `src/api/routes/health.py`：

```python
# src/api/routes/health.py
"""增强版健康检查端点"""
import time

import redis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.core.config import get_settings

router = APIRouter()


def _check_redis() -> dict:
    """检查 Redis 连接状态"""
    try:
        settings = get_settings()
        r = redis.from_url(settings.REDIS_URL)
        start = time.time()
        r.ping()
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def _check_celery() -> dict:
    """检查 Celery worker 是否在线"""
    try:
        from src.core.celery_app import celery_app

        start = time.time()
        response = celery_app.control.ping(timeout=2.0)
        latency_ms = round((time.time() - start) * 1000, 2)
        if response:
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "workers": len(response),
            }
        else:
            return {"status": "unhealthy", "error": "No workers responding"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/health")
def health_check(session: Session = Depends(get_db)):
    """
    平台健康检查 — 免认证。
    检查: database, redis, celery
    """
    components = {}

    # 数据库检查
    try:
        start = time.time()
        session.execute(text("SELECT 1"))
        latency_ms = round((time.time() - start) * 1000, 2)
        components["database"] = {"status": "healthy", "latency_ms": latency_ms}
    except Exception as e:
        components["database"] = {"status": "unhealthy", "error": str(e)}

    # Redis 检查
    components["redis"] = _check_redis()

    # Celery 检查
    components["celery"] = _check_celery()

    # 计算 overall status
    db_status = components["database"]["status"]
    if db_status == "unhealthy":
        overall = "unhealthy"
    elif any(
        c["status"] == "unhealthy"
        for key, c in components.items()
        if key != "database"
    ):
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "components": components,
        "version": "0.1.0",
    }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_api_health.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: 运行全量测试确认无回归**

Run: `pytest tests/ -v`
Expected: All ~183 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/health.py tests/test_api_health.py
git commit -m "feat: 健康检查增强 — 真实 Redis PING + Celery worker 探活"
```

---

### Task 8: Docker Compose + 收尾

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: 扩展 Docker Compose**

`docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: data_platform
      POSTGRES_USER: dp_user
      POSTGRES_PASSWORD: dp_pass
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  celery-worker:
    build: .
    command: celery -A src.core.celery_app worker --loglevel=info --concurrency=4
    depends_on:
      - redis
      - postgres
    environment:
      DATABASE_URL: postgresql://dp_user:dp_pass@postgres:5432/data_platform
      REDIS_URL: redis://redis:6379/0
      ENCRYPTION_KEY: ${ENCRYPTION_KEY:-default-dev-key}
      API_KEY: ${API_KEY:-default-dev-key}

  celery-beat:
    build: .
    command: >
      celery -A src.core.celery_app beat
      --scheduler src.tasks.scheduler:DatabaseScheduler
      --loglevel=info
    depends_on:
      - redis
      - postgres
    environment:
      DATABASE_URL: postgresql://dp_user:dp_pass@postgres:5432/data_platform
      REDIS_URL: redis://redis:6379/0

volumes:
  pgdata:
```

- [ ] **Step 2: 运行全量测试最终确认**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: Docker Compose 添加 celery-worker 和 celery-beat 服务"
```

---

## 任务汇总

| Task | 描述 | 新增测试 | 预计累计 |
|------|------|----------|----------|
| 1 | 依赖与配置基础 | 0 | 158 |
| 2 | Celery 应用实例 | 0 | 158 |
| 3 | _compute_next_run 实现 | +4 | 162 |
| 4 | run_sync_task Celery Task | +9 | 171 |
| 5 | DatabaseScheduler | +6 | 177 |
| 6 | API 层变更（trigger 202） | +3 | ~180 |
| 7 | 健康检查增强 | +3 | ~183 |
| 8 | Docker Compose 收尾 | 0 | ~183 |

**预期最终测试数：~183 个（158 现有 + ~25 新增）**
