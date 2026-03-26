# P1 Sub-project 6: 调度与监控设计

> 日期: 2026-03-26
> 状态: Draft
> 前置: P1 Sub-project 5 (数据服务层 API) 已完成，158 tests passing

## 1. 目标

为数据中台实现基于 Celery Beat 的定时调度系统，将现有的同步执行模式改为异步任务队列模式，并增强健康检查以反映真实的 Redis/Celery 状态。

### 1.1 范围内

- Celery 基础设施搭建（app 实例、配置、Docker 服务）
- 自定义 DatabaseScheduler（从 SyncTask 表动态加载调度）
- Celery task 定义（`run_sync_task`）+ Redis 分布式锁防并发
- 手动触发 API 改为异步入队（200 → 202 Accepted）
- `_compute_next_run` 实现（croniter）
- 健康检查增强（真实 Redis PING + Celery worker 探活）
- 全部测试更新与新增

### 1.2 范围外

- Flower 监控 UI（延后到 P2）
- 告警通知（延后）
- Push 方向的定时调度（当前只支持 pull）

## 2. 架构概览

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  FastAPI API  │────▶│  Redis       │◀────│ Celery Worker│
│  (trigger)    │     │  (broker +   │     │ (run_sync_   │
│               │     │   lock)      │     │  task)        │
└──────────────┘     └──────────────┘     └──────────────┘
                            ▲
                            │
                     ┌──────────────┐     ┌──────────────┐
                     │ Celery Beat  │────▶│ PostgreSQL   │
                     │ (Database    │     │ (SyncTask    │
                     │  Scheduler)  │     │  表)          │
                     └──────────────┘     └──────────────┘
```

**数据流：**
1. Celery Beat（DatabaseScheduler）每 15 秒轮询 `sync_tasks` 表
2. 发现到期任务 → 发送 `run_sync_task` 消息到 Redis broker
3. Celery Worker 消费消息 → 获取 Redis 分布式锁 → 执行同步 → 释放锁
4. 手动触发 API 直接向 Redis broker 发送 `run_sync_task` 消息，返回 202

## 3. Celery 基础设施

### 3.1 配置扩展 (`src/core/config.py`)

在 `Settings` 中新增：

```python
# Celery
CELERY_BROKER_URL: str = ""          # 为空时 fallback 到 REDIS_URL
CELERY_RESULT_BACKEND: str = ""      # 为空时 fallback 到 REDIS_URL

# 调度器
SCHEDULER_SYNC_INTERVAL: int = 15    # Beat 从 DB 刷新调度表的间隔（秒）

# 分布式锁
SYNC_LOCK_TIMEOUT: int = 3600       # 锁自动过期时间（秒），防止死锁

# 任务重试
SYNC_TASK_MAX_RETRIES: int = 3      # 最大重试次数
SYNC_TASK_RETRY_BACKOFF: int = 60   # 首次重试等待（秒），后续指数增长
```

设计决策：`CELERY_BROKER_URL` 和 `CELERY_RESULT_BACKEND` 默认为空字符串，运行时 fallback 到 `REDIS_URL`。开发环境只需配置一个 `REDIS_URL` 即可，生产环境可以分离 broker 和 backend。

### 3.2 Celery 应用实例 (`src/core/celery_app.py`)

新建文件：

```python
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

关键配置说明：
- `task_serializer="json"` — 所有任务参数和结果用 JSON 序列化，与 FastAPI 保持一致
- `acks_late=True`（在 task 装饰器上设置）— 任务完成后才确认，防止 worker 崩溃丢失任务
- `worker_hijack_root_logger=False` — 不劫持根日志，与 FastAPI 日志共存
- `task_track_started=True` — 记录任务开始状态，便于监控

### 3.3 Docker Compose 扩展

在 `docker-compose.yml` 中新增两个服务：

```yaml
celery-worker:
  build: .
  command: celery -A src.core.celery_app worker --loglevel=info --concurrency=4
  depends_on:
    - redis
    - postgres
  environment:
    DATABASE_URL: postgresql://dp_user:dp_pass@postgres:5432/data_platform
    REDIS_URL: redis://redis:6379/0
    ENCRYPTION_KEY: ${ENCRYPTION_KEY}
    API_KEY: ${API_KEY}

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
```

设计决策：
- Beat 和 Worker 分离部署，Beat 只负责调度发消息，不执行任务
- Worker `--concurrency=4` 默认 4 个并发进程，可通过环境变量调整
- Beat 只需要 DB 和 Redis 访问权限，不需要 `ENCRYPTION_KEY`（不解密凭证）

### 3.4 依赖新增

`pyproject.toml` 添加：
- `croniter>=2.0.0` — 计算 cron 表达式的下次执行时间
- `pytest-mock>=3.0.0`（dev 依赖）— 提供 `mocker` fixture

## 4. 自定义 DatabaseScheduler

### 4.1 文件位置

`src/tasks/scheduler.py`

### 4.2 设计

继承 `celery.beat.Scheduler`，核心职责：
1. 定期从 `sync_tasks` 表读取 `enabled=True` 且 `cron_expression IS NOT NULL` 的记录
2. 用 cron_expression 构建 `celery.schedules.crontab` 对象
3. 维护内存调度表（`dict[str, ScheduleEntry]`）
4. 自动发现新增/修改/删除的任务

```python
class DatabaseScheduler(Scheduler):
    """从 SyncTask 表动态加载调度的 Celery Beat Scheduler"""

    def __init__(self, *args, **kwargs):
        self._schedule = {}
        self._last_sync = 0.0
        self.sync_every = settings.SCHEDULER_SYNC_INTERVAL  # 默认 15 秒
        super().__init__(*args, **kwargs)

    def setup_schedule(self):
        """Beat 启动时从 DB 加载"""
        self._sync_from_db()

    def _sync_from_db(self):
        """查询 DB，重建调度表"""
        session = SessionLocal()
        try:
            tasks = session.query(SyncTask).filter(
                SyncTask.enabled == True,
                SyncTask.cron_expression.isnot(None),
            ).all()

            new_schedule = {}
            for task in tasks:
                entry_name = f"sync_task_{task.id}"
                parts = task.cron_expression.split()
                if len(parts) != 5:
                    continue  # 跳过非法 cron 表达式

                schedule = crontab(
                    minute=parts[0], hour=parts[1],
                    day_of_month=parts[2], month_of_year=parts[3],
                    day_of_week=parts[4],
                )
                entry = self.Entry(
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
        """允许父类设置 schedule（初始化时）"""
        self._schedule = value
```

### 4.3 关键设计决策

- **轮询间隔 15 秒**：在响应速度和 DB 负载之间取平衡。创建/修改/删除任务后最多 15 秒生效。
- **保留 `last_run_at`**：刷新调度表时保留已有 entry 的运行状态，避免任务被重复触发。
- **跳过非法 cron**：`len(parts) != 5` 的表达式静默跳过，通过日志记录警告。
- **独立 DB session**：Beat 进程不依赖 FastAPI，自行管理 `SessionLocal`。

## 5. Celery Task 定义

### 5.1 文件结构

```
src/tasks/
├── __init__.py          # 空文件
├── scheduler.py         # DatabaseScheduler
└── sync_tasks.py        # run_sync_task
```

### 5.2 run_sync_task

```python
import logging
import json
import redis
from datetime import datetime, timezone

from src.core.celery_app import celery_app
from src.core.config import get_settings
from src.core.database import SessionLocal
from src.core.security import decrypt_value
from src.connectors.base import connector_registry, ConnectorError
from src.models.connector import Connector
from src.models.sync import SyncTask, SyncLog
from src.services.sync_service import SyncExecutor

logger = logging.getLogger(__name__)
settings = get_settings()
redis_client = redis.from_url(settings.REDIS_URL)


@celery_app.task(
    bind=True,
    name="sync.run_sync_task",
    autoretry_for=(ConnectorError,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
    acks_late=True,
)
def run_sync_task(self, task_id: int):
    """执行单个 SyncTask 的同步"""
    lock = redis_client.lock(
        name=f"sync_lock:{task_id}",
        timeout=settings.SYNC_LOCK_TIMEOUT,
        blocking=False,
    )

    if not lock.acquire(blocking=False):
        logger.info(f"Task {task_id} already running, skipping")
        return {"status": "skipped", "reason": "already_running"}

    session = SessionLocal()
    sync_log = None
    try:
        # 1. 加载任务和连接器
        task = session.query(SyncTask).filter_by(id=task_id).first()
        if not task or not task.enabled:
            logger.warning(f"Task {task_id} not found or disabled")
            return {"status": "skipped", "reason": "not_found_or_disabled"}

        connector_model = session.query(Connector).filter_by(
            id=task.connector_id
        ).first()
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

        # 3. 实例化连接器
        connector_class = connector_registry.get(connector_model.connector_type)
        auth_config = connector_model.auth_config
        if isinstance(auth_config, dict) and "_encrypted" in auth_config:
            decrypted = decrypt_value(
                auth_config["_encrypted"], settings.ENCRYPTION_KEY
            )
            auth_config = json.loads(decrypted)

        config = {
            "base_url": connector_model.base_url,
            "auth_config": auth_config,
        }
        connector = connector_class(config)

        # 4. 执行同步
        try:
            connector.connect()
            if task.direction == "pull":
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
            else:
                sync_log.status = "skipped"
                sync_log.finished_at = datetime.now(timezone.utc)
                result = {"status": "skipped", "reason": "push_not_supported"}
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

### 5.3 并发控制详细设计

| 场景 | 行为 |
|------|------|
| Beat 调度触发，无并发 | 正常获取锁 → 执行 → 释放锁 |
| Beat 调度触发，上次执行未完成 | 获取锁失败 → 返回 `skipped`，不算失败 |
| 手动 trigger，无并发 | 正常获取锁 → 执行 → 释放锁 |
| 手动 trigger，正在执行 | 获取锁失败 → 返回 `skipped` |
| Worker 崩溃未释放锁 | 锁自动过期（`SYNC_LOCK_TIMEOUT` 秒后） |
| 执行时间超过锁超时 | 锁过期释放，新调度可能进入。通过 `LockNotOwnedError` 捕获避免异常 |

### 5.4 重试行为

| 异常类型 | 行为 |
|----------|------|
| `ConnectorError` | 自动重试，最多 3 次，指数退避 60s→120s→240s（上限 600s） |
| 锁获取失败 | 直接跳过，不重试 |
| DB 异常 | 不自动重试，记录错误 |
| 任务/连接器不存在或禁用 | 跳过，不重试 |

### 5.5 `_entity_to_table` 复用

将 `_entity_to_table` 从 `sync_task_service.py` **复制**到 `src/tasks/sync_tasks.py`。两处保持相同实现，但互不依赖。原因：task 层不应反向依赖 service 层，而这个映射函数足够简单（纯 dict lookup），重复优于耦合。如果未来映射逻辑变复杂，可提取到 `src/core/utils.py`。

## 6. API 层变更

### 6.1 手动触发改为异步

`POST /api/v1/sync-tasks/{task_id}/trigger`：

**Before（当前）：**
- 同步执行 pull，返回 200 + 执行结果

**After：**
- 验证 task 和 connector 状态
- 调用 `run_sync_task.delay(task_id)` 入队
- 返回 **202 Accepted** + `{ status, task_id, celery_task_id, message }`

### 6.2 新增响应 Schema

```python
class SyncTaskTriggerResponse(BaseModel):
    status: str           # "accepted"
    task_id: int
    celery_task_id: str
    message: str
```

### 6.3 `sync_task_service.trigger_sync` 重构

原有的完整同步执行逻辑迁移到 `run_sync_task` Celery task 中。service 层的 `trigger_sync` 简化为：

```python
def trigger_sync(session: Session, task_id: int) -> dict:
    """手动触发：验证后入队 Celery task"""
    task = get_sync_task(session, task_id)
    if not task.enabled:
        raise HTTPException(400, "Sync task is disabled")

    connector = session.query(Connector).filter_by(id=task.connector_id).first()
    if not connector or not connector.enabled:
        raise HTTPException(400, "Associated connector not found or disabled")

    from src.tasks.sync_tasks import run_sync_task
    result = run_sync_task.delay(task_id)
    return {
        "status": "accepted",
        "task_id": task_id,
        "celery_task_id": result.id,
        "message": "Sync task has been queued",
    }
```

### 6.4 路由变更

```python
@router.post("/sync-tasks/{task_id}/trigger", status_code=202)
def trigger_sync(task_id: int, session: Session = Depends(get_db)):
    return sync_task_service.trigger_sync(session, task_id)
```

注意：当前路由在调用 `trigger_sync` 后有 `session.commit()`（因为原来同步执行会写 DB）。重构后 `trigger_sync` 只是入队 Celery task，不再写 DB，因此 **移除路由中的 `session.commit()` 调用**。

### 6.5 CRUD 与调度器联动

无需显式通知 Scheduler。DatabaseScheduler 每 15 秒轮询 DB，自动感知：
- 新建任务 → 下次轮询自动加入调度
- 修改 cron_expression → 下次轮询自动更新
- 禁用/删除任务 → 下次轮询自动移除
- Connector soft-delete → 级联 disable SyncTask → 下次轮询自动停止

## 7. 健康检查增强

### 7.1 Redis 检查

替换 `{"status": "not_configured"}`：

```python
def _check_redis() -> dict:
    try:
        r = redis.from_url(get_settings().REDIS_URL)
        start = time.time()
        r.ping()
        latency_ms = round((time.time() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

### 7.2 Celery 检查

```python
def _check_celery() -> dict:
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
```

### 7.3 overall 状态判定

保持现有逻辑不变：

| database | redis | celery | overall |
|----------|-------|--------|---------|
| healthy | healthy | healthy | healthy |
| healthy | unhealthy | * | degraded |
| healthy | * | unhealthy | degraded |
| unhealthy | * | * | unhealthy |

## 8. `_compute_next_run` 实现

在 `src/services/sync_task_service.py` 中，用 `croniter` 替换当前返回 `None` 的 stub：

```python
from croniter import croniter
from datetime import datetime, timezone

def _compute_next_run(cron_expression: str | None) -> datetime | None:
    if not cron_expression:
        return None
    try:
        cron = croniter(cron_expression, datetime.now(timezone.utc))
        return cron.get_next(datetime)
    except (ValueError, KeyError):
        return None
```

## 9. 测试策略

### 9.1 核心原则

- **不启动真实 Redis/Celery**：所有测试通过 mock 运行
- **直接调用 task 函数**：不走 Celery broker，直接调用 `run_sync_task(task_id)`
- **mock 层清晰**：Redis lock、SessionLocal、Celery delay

### 9.2 测试矩阵

| 测试文件 | 类型 | 预估用例 |
|----------|------|----------|
| `tests/test_celery_tasks.py` (新) | 单元 | ~10 |
| `tests/test_scheduler.py` (新) | 单元 | ~6 |
| `tests/test_compute_next_run.py` (新) | 纯函数 | ~4 |
| `tests/test_api_sync_tasks.py` (改) | 集成 | 修改 ~2 |
| `tests/test_api_health.py` (改) | 集成 | 修改 ~4, 新增 ~2 |

预计新增 **~22** 个测试，总计 **~180** 个。

### 9.3 Celery task 测试示例

```python
def test_run_sync_task_success(db_session, mocker):
    # mock Redis lock
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = True
    mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock)
    mocker.patch("src.tasks.sync_tasks.SessionLocal", return_value=db_session)

    # 创建测试数据...
    result = run_sync_task(task_id)
    assert result["status"] == "success"
    # 验证 SyncLog 已创建...

def test_run_sync_task_lock_conflict(mocker):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = False
    mocker.patch("src.tasks.sync_tasks.redis_client.lock", return_value=mock_lock)

    result = run_sync_task(task_id)
    assert result["status"] == "skipped"
    assert result["reason"] == "already_running"
```

### 9.4 API trigger 测试变更

```python
def test_trigger_returns_202(client, db_session, api_headers, mocker):
    mock_result = MagicMock()
    mock_result.id = "fake-celery-id"
    mocker.patch(
        "src.services.sync_task_service.run_sync_task.delay",
        return_value=mock_result,
    )
    response = client.post(f"/api/v1/sync-tasks/{task_id}/trigger", headers=api_headers)
    assert response.status_code == 202
    assert response.json()["celery_task_id"] == "fake-celery-id"
```

### 9.5 健康检查测试变更

```python
def test_health_all_healthy(client, mocker):
    mocker.patch("src.api.routes.health._check_redis",
                 return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery",
                 return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/health")
    assert resp.json()["status"] == "healthy"

def test_health_redis_down_degraded(client, mocker):
    mocker.patch("src.api.routes.health._check_redis",
                 return_value={"status": "unhealthy", "error": "Connection refused"})
    mocker.patch("src.api.routes.health._check_celery",
                 return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/health")
    assert resp.json()["status"] == "degraded"
```

## 10. 文件变更清单

### 新增文件
| 文件 | 描述 |
|------|------|
| `src/core/celery_app.py` | Celery 应用实例 |
| `src/tasks/__init__.py` | 包标识（空文件） |
| `src/tasks/scheduler.py` | DatabaseScheduler |
| `src/tasks/sync_tasks.py` | run_sync_task Celery task |
| `tests/test_celery_tasks.py` | task 单元测试 |
| `tests/test_scheduler.py` | scheduler 单元测试 |
| `tests/test_compute_next_run.py` | croniter 纯函数测试 |

### 修改文件
| 文件 | 变更 |
|------|------|
| `src/core/config.py` | 新增 Celery/Scheduler/Lock/Retry 配置项 |
| `src/services/sync_task_service.py` | trigger_sync 改为入队；_compute_next_run 用 croniter 实现；移除内联同步逻辑 |
| `src/api/routes/sync_tasks.py` | trigger 路由返回 202 |
| `src/api/routes/health.py` | 真实 Redis/Celery 检查 |
| `src/api/schemas/sync.py` | 新增 SyncTaskTriggerResponse |
| `docker-compose.yml` | 新增 celery-worker、celery-beat 服务 |
| `pyproject.toml` | 新增 croniter、pytest-mock 依赖 |
| `tests/test_api_sync_tasks.py` | trigger 测试改为 202 |
| `tests/test_api_health.py` | mock Redis/Celery 检查 |

## 11. 已知约束与未来改进

- **轮询延迟**：任务变更最多 15 秒后生效。如需即时响应，未来可加 Redis pub/sub 通知。
- **Push 调度**：当前只支持 pull 方向的定时调度，push 方向的定时调度留待后续需求。
- **锁超时风险**：如果同步执行时间超过 `SYNC_LOCK_TIMEOUT`，锁会提前释放。生产环境需根据实际执行时间调整此值。
- **Flower**：可在 P2 管理后台中集成 Flower 或自建 Celery 监控面板。
- **告警**：可在后续子项目中添加任务连续失败告警（飞书/邮件通知）。
