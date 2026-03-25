# P1 子项目5：数据服务层 API 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为数据中台添加完整的 REST API 层，包括认证、错误处理、CRUD、数据查询、数据回写和健康检查。

**Architecture:** 扁平路由 + 独立服务。每个 API 端点组一个路由文件 (`src/api/routes/`)，每组对应一个服务类 (`src/services/`)。共享依赖 (认证、分页、DB session) 集中在 `src/api/deps.py`。统一错误处理在 `src/api/errors.py`。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest + TestClient + SQLite in-memory。

**Spec:** `docs/superpowers/specs/2026-03-25-p1-data-service-api-design.md`

**Existing tests:** 100 tests passing. Run `pytest` from project root to verify.

---

## File Structure

### New files to create:

| File | Responsibility |
|------|---------------|
| `src/api/deps.py` | API Key 认证依赖 `get_current_api_key()`、DB session 依赖 `get_db()`、分页参数 `PaginationParams`、分页工具 `paginate()` |
| `src/api/errors.py` | 全局 exception handlers: HTTPException, RequestValidationError, 500 catch-all |
| `src/api/schemas/__init__.py` | 包导出 |
| `src/api/schemas/common.py` | `ErrorDetail`, `ErrorResponse`, `PaginatedResponse[T]` |
| `src/api/schemas/connector.py` | `ConnectorCreate`, `ConnectorUpdate`, `ConnectorResponse` |
| `src/api/schemas/sync.py` | `SyncTaskCreate`, `SyncTaskUpdate`, `SyncTaskResponse`, `SyncLogResponse` |
| `src/api/schemas/data.py` | `PushRequest`, `PushResponse` |
| `src/api/routes/__init__.py` | 包导出 |
| `src/api/routes/health.py` | 增强版健康检查 (替换 `src/api/health.py`) |
| `src/api/routes/connectors.py` | 连接器 CRUD 路由 |
| `src/api/routes/sync_tasks.py` | 同步任务 CRUD + 触发路由 |
| `src/api/routes/sync_logs.py` | 同步日志查询路由 |
| `src/api/routes/data.py` | 统一数据 + 原始数据查询路由 |
| `src/api/routes/push.py` | 数据回写路由 |
| `src/services/connector_service.py` | 连接器 CRUD 服务 + 凭证加密 + 软删除级联 |
| `src/services/sync_task_service.py` | 同步任务管理服务 + 触发执行 + 同步日志查询 |
| `src/services/push_service.py` | 数据推送服务 (连接器实例化 + 连接管理) |
| `tests/test_api_deps.py` | 认证 + 分页测试 |
| `tests/test_api_errors.py` | 统一错误格式测试 |
| `tests/test_api_connectors.py` | 连接器 CRUD 测试 |
| `tests/test_api_sync_tasks.py` | 同步任务 CRUD + 触发测试 |
| `tests/test_api_sync_logs.py` | 同步日志查询测试 |
| `tests/test_api_data.py` | 统一/原始数据查询测试 |
| `tests/test_api_push.py` | 数据推送测试 |

### Files to modify:

| File | Changes |
|------|---------|
| `src/main.py` | 完全重写：注册所有路由、错误处理、startup 事件 |
| `src/models/sync.py` | `cron_expression` 改为 `nullable=True` |
| `tests/conftest.py` | 添加 `client` fixture (TestClient with DB override)、`api_headers` fixture |
| `tests/test_api_health.py` | 重写为增强版健康检查测试 |

### Files to delete:

| File | Reason |
|------|--------|
| `src/api/health.py` | 功能移至 `src/api/routes/health.py` |

---

## Key Patterns for All Tasks

### TestClient + DB Override Pattern (Connection-Level Transaction)

所有 API 测试共享此模式。**关键点**：路由中调用 `session.commit()` 会永久提交数据。为保证测试隔离，`db_session` fixture 使用 connection-level transaction 包裹 session —— 即使路由内 commit 了，外层 transaction 在 teardown 时 rollback 也能撤销一切。

```python
# tests/conftest.py — 完整版
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-for-testing")

import src.models  # noqa: F401
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from src.models.base import Base

@pytest.fixture(scope="session")
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine

@pytest.fixture
def db_session(engine):
    """每个测试用 connection-level transaction 包裹，确保测试隔离。
    路由中的 session.commit() 实际 commit 到 savepoint，
    teardown 时外层 transaction rollback 撤销一切。"""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    # 让 session.commit() 变成 flush (不真正提交外层事务)
    # 使用 begin_nested 在 commit 时创建 savepoint
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    session.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session):
    from fastapi.testclient import TestClient
    from src.main import app
    from src.api.deps import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture
def api_headers():
    return {"Authorization": "Bearer test-api-key"}
```

测试时需要环境变量 `API_KEY=test-api-key`、`DATABASE_URL=sqlite:///:memory:`、`REDIS_URL=redis://localhost`、`ENCRYPTION_KEY=test-key`（已在 conftest.py 顶部通过 `os.environ.setdefault` 设置）。

---

## Task 1: 基础设施层 — Schemas + Deps + Errors

**Files:**
- Create: `src/api/schemas/__init__.py`
- Create: `src/api/schemas/common.py`
- Create: `src/api/deps.py`
- Create: `src/api/errors.py`
- Create: `tests/test_api_deps.py`
- Create: `tests/test_api_errors.py`
- Modify: `src/main.py`
- Modify: `tests/conftest.py`

**Why first:** All other tasks depend on deps (auth, pagination, DB session), schemas (error format), and error handlers. main.py must be updated to register error handlers and have `get_db` before any API route can be tested.

### Steps:

- [ ] **Step 1: Update conftest.py with test infrastructure**

Replace `tests/conftest.py` with the connection-level transaction pattern (see Key Patterns above for rationale):

```python
import os
# 设置测试环境变量 — 必须在导入 app 之前
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-for-testing")

import src.models  # noqa: F401

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from src.models.base import Base


@pytest.fixture(scope="session")
def engine():
    """使用 SQLite 内存数据库做测试"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(engine):
    """每个测试用 connection-level transaction 包裹，确保测试隔离。"""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    session.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient，覆盖 DB session 依赖"""
    from fastapi.testclient import TestClient
    from src.main import app
    from src.api.deps import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def api_headers():
    """带有效 API Key 的请求头"""
    return {"Authorization": "Bearer test-api-key"}
```

- [ ] **Step 2: Create schemas/common.py**

Create `src/api/schemas/__init__.py` (empty) and `src/api/schemas/common.py`:

```python
# src/api/schemas/common.py
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total_count: int
    page: int
    page_size: int
```

- [ ] **Step 3: Create deps.py**

Create `src/api/deps.py`:

```python
# src/api/deps.py
from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.database import get_session


def get_db():
    """数据库 session 依赖（可在测试中 override）"""
    yield from get_session()


def get_current_api_key(request: Request) -> str:
    """API Key 认证依赖。从 Authorization: Bearer <key> 或 X-API-Key 头提取。"""
    settings = get_settings()

    # 尝试 Authorization: Bearer <key>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token == settings.API_KEY:
            return token

    # 尝试 X-API-Key
    api_key = request.headers.get("X-API-Key", "")
    if api_key == settings.API_KEY:
        return api_key

    raise HTTPException(status_code=401, detail="Invalid or missing API key")


class PaginationParams:
    """分页参数依赖"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def paginate(query, params: PaginationParams) -> dict:
    """对 SQLAlchemy query 应用分页，返回标准分页响应字典。"""
    total_count = query.count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return {
        "items": items,
        "total_count": total_count,
        "page": params.page,
        "page_size": params.page_size,
    }
```

- [ ] **Step 4: Create errors.py**

Create `src/api/errors.py`:

```python
# src/api/errors.py
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# HTTP 状态码 → 错误码映射
STATUS_CODE_MAP = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
}


def register_error_handlers(app: FastAPI) -> None:
    """注册全局异常处理器"""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        code = STATUS_CODE_MAP.get(exc.status_code, "ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": str(exc.detail),
                    "details": None,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal server error",
                    "details": None,
                }
            },
        )
```

- [ ] **Step 5: Create minimal routes/__init__.py and routes/health.py stub**

Create `src/api/routes/__init__.py` (empty) and a minimal `src/api/routes/health.py` that just returns `{"status": "healthy"}` — the full implementation comes in Task 7. This is needed so `main.py` can import it.

```python
# src/api/routes/health.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    """健康检查 — 简化版，Task 7 增强"""
    return {
        "status": "healthy",
        "components": {
            "database": {"status": "not_configured"},
            "redis": {"status": "not_configured"},
            "celery": {"status": "not_configured"},
        },
        "version": "0.1.0",
    }
```

- [ ] **Step 6: Rewrite main.py**

Replace `src/main.py` with the new version that registers error handlers and uses the new route structure:

```python
# src/main.py
from fastapi import FastAPI

from src.api.errors import register_error_handlers
from src.api.routes.health import router as health_router

app = FastAPI(title="数据中台", version="0.1.0")

# 注册统一错误处理
register_error_handlers(app)

# 注册路由 — 健康检查免认证
app.include_router(health_router, prefix="/api/v1", tags=["health"])


@app.get("/")
def root():
    return {"name": "数据中台", "version": "0.1.0"}
```

Note: More routers will be added in subsequent tasks as they are created.

- [ ] **Step 7: Delete old health.py**

Delete `src/api/health.py` (replaced by `src/api/routes/health.py`).

- [ ] **Step 8: Rewrite test_api_health.py to use client fixture**

The existing `test_api_health.py` uses a module-level `TestClient(app)` which will break after `main.py` changes. Rewrite it to use the `client` fixture:

```python
# tests/test_api_health.py
"""健康检查 API 测试"""


def test_root(client):
    """根路径应返回应用信息"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "数据中台"


def test_health_endpoint(client):
    """健康检查端点应返回状态"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in ("healthy", "degraded", "unhealthy")


def test_health_no_auth_required(client):
    """健康检查免认证"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
```

- [ ] **Step 9: Write test_api_deps.py — auth tests**

Create `tests/test_api_deps.py`:

```python
# tests/test_api_deps.py
"""API 认证和分页依赖测试"""


class TestAPIKeyAuth:
    """API Key 认证测试"""

    def test_valid_bearer_token(self, client, api_headers):
        """有效 Bearer token 应通过认证"""
        resp = client.get("/api/v1/health", headers=api_headers)
        assert resp.status_code == 200

    def test_valid_x_api_key(self, client):
        """有效 X-API-Key 头应通过认证"""
        resp = client.get("/api/v1/health", headers={"X-API-Key": "test-api-key"})
        assert resp.status_code == 200

    def test_missing_api_key(self, client):
        """健康检查免认证"""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_invalid_bearer_token(self, client):
        """健康检查免认证，即使 token 无效也返回 200"""
        resp = client.get("/api/v1/health", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 200


class TestPaginationParams:
    """分页参数测试"""

    def test_pagination_defaults(self):
        """默认分页参数"""
        from src.api.deps import PaginationParams
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 20
        assert params.offset == 0

    def test_pagination_offset_calculation(self):
        """分页偏移计算"""
        from src.api.deps import PaginationParams
        params = PaginationParams(page=3, page_size=10)
        assert params.offset == 20
```

- [ ] **Step 10: Write test_api_errors.py**

Create `tests/test_api_errors.py`:

```python
# tests/test_api_errors.py
"""统一错误响应格式测试"""


def test_error_response_structure(client):
    """错误响应应包含 error.code 和 error.message"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_health_returns_valid_json(client):
    """健康检查应返回有效 JSON"""
    resp = client.get("/api/v1/health")
    data = resp.json()
    assert "status" in data
```

- [ ] **Step 11: Run all tests to verify nothing is broken**

Run: `pytest -v`
Expected: All 100 existing tests + new tests pass (test_api_health.py rewritten, existing tests unaffected).

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat: 添加 API 基础设施层 — 认证、分页、错误处理、schemas"
```

---

## Task 2: Pydantic Schemas (Connector / Sync / Data)

**Files:**
- Create: `src/api/schemas/connector.py`
- Create: `src/api/schemas/sync.py`
- Create: `src/api/schemas/data.py`
- Modify: `src/api/schemas/__init__.py`

**Why now:** Services and routes in Tasks 3-6 will import these schemas. Define them all at once to avoid circular deps.

### Steps:

- [ ] **Step 1: Create connector schemas**

Create `src/api/schemas/connector.py`:

```python
# src/api/schemas/connector.py
from datetime import datetime

from pydantic import BaseModel, Field


class ConnectorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    connector_type: str = Field(..., min_length=1, max_length=50)
    base_url: str = Field(..., min_length=1, max_length=500)
    auth_config: dict = Field(default_factory=dict)
    description: str | None = None


class ConnectorUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    connector_type: str | None = Field(None, min_length=1, max_length=50)
    base_url: str | None = Field(None, min_length=1, max_length=500)
    auth_config: dict | None = None
    description: str | None = None
    enabled: bool | None = None


class ConnectorResponse(BaseModel):
    id: int
    name: str
    connector_type: str
    base_url: str
    has_auth_config: bool
    enabled: bool
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Create sync schemas**

Create `src/api/schemas/sync.py`:

```python
# src/api/schemas/sync.py
from datetime import datetime

from pydantic import BaseModel, Field


class SyncTaskCreate(BaseModel):
    connector_id: int
    entity: str = Field(..., min_length=1, max_length=100)
    direction: str = Field(..., pattern="^(pull|push)$")
    cron_expression: str | None = Field(None, max_length=100)
    enabled: bool = True


class SyncTaskUpdate(BaseModel):
    entity: str | None = Field(None, min_length=1, max_length=100)
    direction: str | None = Field(None, pattern="^(pull|push)$")
    cron_expression: str | None = None
    enabled: bool | None = None


class SyncTaskResponse(BaseModel):
    id: int
    connector_id: int
    entity: str
    direction: str
    cron_expression: str | None
    enabled: bool
    last_sync_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SyncLogResponse(BaseModel):
    id: int
    sync_task_id: int | None
    connector_id: int
    entity: str
    direction: str
    status: str
    total_records: int
    success_count: int
    failure_count: int
    error_details: dict | None
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Create data schemas**

Create `src/api/schemas/data.py`:

```python
# src/api/schemas/data.py
from pydantic import BaseModel, Field


class PushRequest(BaseModel):
    records: list[dict] = Field(..., min_length=1)


class PushResponse(BaseModel):
    success_count: int
    failure_count: int
    failures: list[dict] = Field(default_factory=list)
```

- [ ] **Step 4: Update schemas __init__.py**

Update `src/api/schemas/__init__.py`:

```python
# src/api/schemas/__init__.py
from src.api.schemas.common import ErrorDetail, ErrorResponse, PaginatedResponse  # noqa: F401
from src.api.schemas.connector import (  # noqa: F401
    ConnectorCreate, ConnectorUpdate, ConnectorResponse,
)
from src.api.schemas.sync import (  # noqa: F401
    SyncTaskCreate, SyncTaskUpdate, SyncTaskResponse, SyncLogResponse,
)
from src.api.schemas.data import PushRequest, PushResponse  # noqa: F401
```

- [ ] **Step 5: Run tests to verify**

Run: `pytest -v`
Expected: All tests pass (no behavior change, just new schema files).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: 添加 Pydantic schemas — connector, sync, data"
```

---

## Task 3: 连接器管理 API (Connector CRUD)

**Files:**
- Create: `src/services/connector_service.py`
- Create: `src/api/routes/connectors.py`
- Create: `tests/test_api_connectors.py`
- Modify: `src/main.py` (add connectors router)
- Modify: `src/models/sync.py` (`cron_expression` → nullable)

**Why now:** Connectors are the foundation — sync tasks and push both reference connectors.

### Steps:

- [ ] **Step 1: Update SyncTask model — cron_expression nullable**

Edit `src/models/sync.py:19`:

```python
# Change from:
cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
# Change to:
cron_expression: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

- [ ] **Step 2: Write connector_service.py**

Create `src/services/connector_service.py`:

```python
# src/services/connector_service.py
"""连接器管理服务：CRUD + 凭证加密 + 软删除级联"""
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.api.deps import PaginationParams, paginate
from src.connectors.base import connector_registry
from src.core.config import get_settings
from src.core.security import encrypt_value, decrypt_value
from src.models.connector import Connector
from src.models.sync import SyncTask


def list_connectors(session: Session, params: PaginationParams) -> dict:
    """分页列出所有连接器"""
    query = session.query(Connector).order_by(Connector.id)
    return paginate(query, params)


def get_connector(session: Session, connector_id: int) -> Connector:
    """按 ID 获取连接器，不存在则 404"""
    connector = session.query(Connector).filter_by(id=connector_id).first()
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector with id {connector_id} not found")
    return connector


def create_connector(session: Session, data: dict) -> Connector:
    """创建连接器，加密凭证"""
    # 验证 connector_type
    valid_types = connector_registry.list_types()
    if data["connector_type"] not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid connector type: {data['connector_type']}. Valid: {valid_types}",
        )

    # 检查名称唯一性
    existing = session.query(Connector).filter_by(name=data["name"]).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Connector name '{data['name']}' already exists")

    # 加密 auth_config
    auth_config = data.get("auth_config", {})
    settings = get_settings()
    if auth_config and settings.ENCRYPTION_KEY:
        encrypted = encrypt_value(json.dumps(auth_config), settings.ENCRYPTION_KEY)
        auth_config = {"_encrypted": encrypted}

    connector = Connector(
        name=data["name"],
        connector_type=data["connector_type"],
        base_url=data["base_url"],
        auth_config=auth_config,
        description=data.get("description"),
    )
    session.add(connector)
    session.flush()
    return connector


def update_connector(session: Session, connector_id: int, data: dict) -> Connector:
    """更新连接器配置"""
    connector = get_connector(session, connector_id)

    # 如果更新 connector_type，验证
    if "connector_type" in data and data["connector_type"] is not None:
        valid_types = connector_registry.list_types()
        if data["connector_type"] not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid connector type: {data['connector_type']}. Valid: {valid_types}",
            )

    # 如果更新 name，检查唯一性
    if "name" in data and data["name"] is not None and data["name"] != connector.name:
        existing = session.query(Connector).filter_by(name=data["name"]).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Connector name '{data['name']}' already exists")

    for key, value in data.items():
        if value is None:
            continue
        if key == "auth_config":
            settings = get_settings()
            if value and settings.ENCRYPTION_KEY:
                encrypted = encrypt_value(json.dumps(value), settings.ENCRYPTION_KEY)
                value = {"_encrypted": encrypted}
            setattr(connector, key, value)
        elif hasattr(connector, key):
            setattr(connector, key, value)

    session.flush()
    return connector


def delete_connector(session: Session, connector_id: int) -> None:
    """软删除：禁用连接器 + 级联禁用关联同步任务"""
    connector = get_connector(session, connector_id)
    connector.enabled = False

    # 级联禁用关联的同步任务
    sync_tasks = session.query(SyncTask).filter_by(connector_id=connector_id).all()
    for task in sync_tasks:
        task.enabled = False

    session.flush()


def connector_to_response(connector: Connector) -> dict:
    """将 Connector ORM 对象转为响应字典（隐藏 auth_config）"""
    return {
        "id": connector.id,
        "name": connector.name,
        "connector_type": connector.connector_type,
        "base_url": connector.base_url,
        "has_auth_config": bool(connector.auth_config),
        "enabled": connector.enabled,
        "description": connector.description,
        "created_at": connector.created_at,
        "updated_at": connector.updated_at,
    }
```

- [ ] **Step 3: Write routes/connectors.py**

Create `src/api/routes/connectors.py`:

```python
# src/api/routes/connectors.py
"""连接器管理 API 路由"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key, PaginationParams
from src.api.schemas.connector import ConnectorCreate, ConnectorUpdate
from src.services import connector_service

router = APIRouter(dependencies=[Depends(get_current_api_key)])


@router.get("/connectors")
def list_connectors(
    params: PaginationParams = Depends(),
    session: Session = Depends(get_db),
):
    result = connector_service.list_connectors(session, params)
    result["items"] = [connector_service.connector_to_response(c) for c in result["items"]]
    return result


@router.post("/connectors", status_code=201)
def create_connector(
    data: ConnectorCreate,
    session: Session = Depends(get_db),
):
    connector = connector_service.create_connector(session, data.model_dump())
    session.commit()
    return connector_service.connector_to_response(connector)


@router.get("/connectors/{connector_id}")
def get_connector(
    connector_id: int,
    session: Session = Depends(get_db),
):
    connector = connector_service.get_connector(session, connector_id)
    return connector_service.connector_to_response(connector)


@router.put("/connectors/{connector_id}")
def update_connector(
    connector_id: int,
    data: ConnectorUpdate,
    session: Session = Depends(get_db),
):
    connector = connector_service.update_connector(
        session, connector_id, data.model_dump(exclude_unset=True)
    )
    session.commit()
    return connector_service.connector_to_response(connector)


@router.delete("/connectors/{connector_id}", status_code=204)
def delete_connector(
    connector_id: int,
    session: Session = Depends(get_db),
):
    connector_service.delete_connector(session, connector_id)
    session.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Register connectors router in main.py**

Add to `src/main.py`:

```python
from src.api.routes.connectors import router as connectors_router
app.include_router(connectors_router, prefix="/api/v1", tags=["connectors"])
```

- [ ] **Step 5: Write test_api_connectors.py**

Create `tests/test_api_connectors.py`:

```python
# tests/test_api_connectors.py
"""连接器管理 API 测试"""
import pytest


@pytest.fixture
def sample_connector_data():
    return {
        "name": "测试金蝶ERP",
        "connector_type": "kingdee_erp",
        "base_url": "https://erp.test.com",
        "auth_config": {"acct_id": "test", "username": "admin", "password": "secret"},
        "description": "测试环境",
    }


class TestCreateConnector:
    def test_create_success(self, client, api_headers, sample_connector_data):
        resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "测试金蝶ERP"
        assert data["connector_type"] == "kingdee_erp"
        assert data["enabled"] is True
        assert data["has_auth_config"] is True
        assert "auth_config" not in data  # 凭证不暴露

    def test_create_invalid_type(self, client, api_headers):
        resp = client.post("/api/v1/connectors", json={
            "name": "bad", "connector_type": "invalid", "base_url": "http://x",
        }, headers=api_headers)
        assert resp.status_code == 400

    def test_create_duplicate_name(self, client, api_headers, sample_connector_data):
        client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        assert resp.status_code == 409

    def test_create_requires_auth(self, client, sample_connector_data):
        resp = client.post("/api/v1/connectors", json=sample_connector_data)
        assert resp.status_code == 401


class TestListConnectors:
    def test_list_empty(self, client, api_headers):
        resp = client.get("/api/v1/connectors", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total_count"] == 0

    def test_list_with_pagination(self, client, api_headers, sample_connector_data):
        # 创建 2 个连接器
        client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        data2 = {**sample_connector_data, "name": "第二个"}
        client.post("/api/v1/connectors", json=data2, headers=api_headers)
        resp = client.get("/api/v1/connectors?page=1&page_size=1", headers=api_headers)
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total_count"] == 2


class TestGetConnector:
    def test_get_success(self, client, api_headers, sample_connector_data):
        create_resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        cid = create_resp.json()["id"]
        resp = client.get(f"/api/v1/connectors/{cid}", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "测试金蝶ERP"

    def test_get_not_found(self, client, api_headers):
        resp = client.get("/api/v1/connectors/999", headers=api_headers)
        assert resp.status_code == 404


class TestUpdateConnector:
    def test_update_success(self, client, api_headers, sample_connector_data):
        create_resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        cid = create_resp.json()["id"]
        resp = client.put(f"/api/v1/connectors/{cid}", json={"name": "新名称"}, headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "新名称"


class TestDeleteConnector:
    def test_soft_delete(self, client, api_headers, sample_connector_data):
        create_resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        cid = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/connectors/{cid}", headers=api_headers)
        assert resp.status_code == 204
        # 验证已禁用
        get_resp = client.get(f"/api/v1/connectors/{cid}", headers=api_headers)
        assert get_resp.json()["enabled"] is False

    def test_delete_cascades_sync_tasks(self, client, api_headers, sample_connector_data, db_session):
        """软删除应级联禁用关联的同步任务"""
        create_resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        cid = create_resp.json()["id"]
        # 通过 DB 直接添加同步任务（因为同步任务 API 还没实现）
        from src.models.sync import SyncTask
        task = SyncTask(connector_id=cid, entity="order", direction="pull", enabled=True)
        db_session.add(task)
        db_session.flush()
        task_id = task.id

        client.delete(f"/api/v1/connectors/{cid}", headers=api_headers)

        refreshed_task = db_session.query(SyncTask).filter_by(id=task_id).first()
        assert refreshed_task.enabled is False
```

- [ ] **Step 6: Run tests**

Run: `pytest -v`
Expected: All existing + ~11 new tests pass.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: 实现连接器管理 API — CRUD + 软删除 + 凭证加密"
```

---

## Task 4: 同步任务管理 API (Sync Tasks + Logs)

**Files:**
- Create: `src/services/sync_task_service.py`
- Create: `src/api/routes/sync_tasks.py`
- Create: `src/api/routes/sync_logs.py`
- Create: `tests/test_api_sync_tasks.py`
- Create: `tests/test_api_sync_logs.py`
- Modify: `src/main.py` (add sync routers)

### Steps:

- [ ] **Step 1: Write sync_task_service.py**

Create `src/services/sync_task_service.py`:

```python
# src/services/sync_task_service.py
"""同步任务管理服务：CRUD + 验证 + 触发执行 + 日志查询"""
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.api.deps import PaginationParams, paginate
from src.connectors.base import connector_registry, ConnectorError
from src.core.config import get_settings
from src.core.security import decrypt_value
from src.models.connector import Connector
from src.models.sync import SyncTask, SyncLog
from src.services.sync_service import SyncExecutor


def list_sync_tasks(session: Session, params: PaginationParams) -> dict:
    """分页列出同步任务"""
    query = session.query(SyncTask).order_by(SyncTask.id)
    return paginate(query, params)


def get_sync_task(session: Session, task_id: int) -> SyncTask:
    """按 ID 获取同步任务"""
    task = session.query(SyncTask).filter_by(id=task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Sync task with id {task_id} not found")
    return task


def create_sync_task(session: Session, data: dict) -> SyncTask:
    """创建同步任务，验证 connector_id 和 entity"""
    # 验证 connector 存在且启用
    connector = session.query(Connector).filter_by(id=data["connector_id"]).first()
    if not connector or not connector.enabled:
        raise HTTPException(status_code=400, detail="Connector not found or disabled")

    task = SyncTask(
        connector_id=data["connector_id"],
        entity=data["entity"],
        direction=data["direction"],
        cron_expression=data.get("cron_expression"),
        enabled=data.get("enabled", True),
    )
    session.add(task)
    session.flush()
    return task


def update_sync_task(session: Session, task_id: int, data: dict) -> SyncTask:
    """更新同步任务"""
    task = get_sync_task(session, task_id)
    for key, value in data.items():
        if value is not None and hasattr(task, key):
            setattr(task, key, value)
    session.flush()
    return task


def delete_sync_task(session: Session, task_id: int) -> None:
    """删除同步任务"""
    task = get_sync_task(session, task_id)
    session.delete(task)
    session.flush()


def trigger_sync(session: Session, task_id: int) -> dict:
    """手动触发同步（同步执行）"""
    task = get_sync_task(session, task_id)
    if not task.enabled:
        raise HTTPException(status_code=400, detail="Sync task is disabled")

    connector_model = session.query(Connector).filter_by(id=task.connector_id).first()
    if not connector_model or not connector_model.enabled:
        raise HTTPException(status_code=400, detail="Associated connector not found or disabled")

    # 实例化连接器
    connector_class = connector_registry.get(connector_model.connector_type)
    auth_config = connector_model.auth_config

    # 解密凭证
    settings = get_settings()
    if isinstance(auth_config, dict) and "_encrypted" in auth_config:
        decrypted = decrypt_value(auth_config["_encrypted"], settings.ENCRYPTION_KEY)
        auth_config = json.loads(decrypted)

    config = {
        "base_url": connector_model.base_url,
        "auth_config": auth_config,
    }
    connector = connector_class(config)

    try:
        connector.connect()

        if task.direction == "pull":
            executor = SyncExecutor()
            # 确定目标表 — 简单映射
            target_table = _entity_to_table(task.entity)
            result = executor.execute_pull(
                connector=connector,
                connector_id=connector_model.id,
                entity=task.entity,
                target_table=target_table,
                mappings=[],  # 空映射，直接存储
                session=session,
                since=task.last_sync_at,
            )
        else:
            # push 方向暂不支持自动触发
            result = {"status": "error", "message": "Push trigger not supported yet"}

        # 更新 last_sync_at
        task.last_sync_at = datetime.now(timezone.utc)
        session.flush()

        return result
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=f"Connector error: {str(e)}")
    finally:
        try:
            connector.disconnect()
        except Exception:
            pass


def list_sync_logs(
    session: Session,
    params: PaginationParams,
    connector_id: int | None = None,
    entity: str | None = None,
    status: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
) -> dict:
    """分页查询同步日志，支持过滤"""
    query = session.query(SyncLog).order_by(SyncLog.started_at.desc())
    if connector_id is not None:
        query = query.filter(SyncLog.connector_id == connector_id)
    if entity is not None:
        query = query.filter(SyncLog.entity == entity)
    if status is not None:
        query = query.filter(SyncLog.status == status)
    if started_after is not None:
        query = query.filter(SyncLog.started_at >= started_after)
    if started_before is not None:
        query = query.filter(SyncLog.started_at <= started_before)
    return paginate(query, params)


def sync_task_to_response(task: SyncTask) -> dict:
    """将 SyncTask ORM 转为响应字典"""
    return {
        "id": task.id,
        "connector_id": task.connector_id,
        "entity": task.entity,
        "direction": task.direction,
        "cron_expression": task.cron_expression,
        "enabled": task.enabled,
        "last_sync_at": task.last_sync_at,
        "next_run_at": _compute_next_run(task.cron_expression),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def sync_log_to_response(log: SyncLog) -> dict:
    """将 SyncLog ORM 转为响应字典"""
    return {
        "id": log.id,
        "sync_task_id": log.sync_task_id,
        "connector_id": log.connector_id,
        "entity": log.entity,
        "direction": log.direction,
        "status": log.status,
        "total_records": log.total_records,
        "success_count": log.success_count,
        "failure_count": log.failure_count,
        "error_details": log.error_details,
        "started_at": log.started_at,
        "finished_at": log.finished_at,
    }


def _compute_next_run(cron_expression: str | None) -> datetime | None:
    """从 cron 表达式计算下次运行时间。无 cron 返回 None。"""
    if not cron_expression:
        return None
    # 简单实现：不安装 croniter 依赖，返回 None
    # 子项目6 接入 Celery Beat 后用真实调度器计算
    return None


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
```

- [ ] **Step 2: Write routes/sync_tasks.py**

Create `src/api/routes/sync_tasks.py`:

```python
# src/api/routes/sync_tasks.py
"""同步任务管理 API 路由"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key, PaginationParams
from src.api.schemas.sync import SyncTaskCreate, SyncTaskUpdate
from src.services import sync_task_service

router = APIRouter(dependencies=[Depends(get_current_api_key)])


@router.get("/sync-tasks")
def list_sync_tasks(
    params: PaginationParams = Depends(),
    session: Session = Depends(get_db),
):
    result = sync_task_service.list_sync_tasks(session, params)
    result["items"] = [sync_task_service.sync_task_to_response(t) for t in result["items"]]
    return result


@router.post("/sync-tasks", status_code=201)
def create_sync_task(
    data: SyncTaskCreate,
    session: Session = Depends(get_db),
):
    task = sync_task_service.create_sync_task(session, data.model_dump())
    session.commit()
    return sync_task_service.sync_task_to_response(task)


@router.get("/sync-tasks/{task_id}")
def get_sync_task(
    task_id: int,
    session: Session = Depends(get_db),
):
    task = sync_task_service.get_sync_task(session, task_id)
    return sync_task_service.sync_task_to_response(task)


@router.put("/sync-tasks/{task_id}")
def update_sync_task(
    task_id: int,
    data: SyncTaskUpdate,
    session: Session = Depends(get_db),
):
    task = sync_task_service.update_sync_task(session, task_id, data.model_dump(exclude_unset=True))
    session.commit()
    return sync_task_service.sync_task_to_response(task)


@router.delete("/sync-tasks/{task_id}", status_code=204)
def delete_sync_task(
    task_id: int,
    session: Session = Depends(get_db),
):
    sync_task_service.delete_sync_task(session, task_id)
    session.commit()
    return Response(status_code=204)


@router.post("/sync-tasks/{task_id}/trigger")
def trigger_sync(
    task_id: int,
    session: Session = Depends(get_db),
):
    result = sync_task_service.trigger_sync(session, task_id)
    session.commit()
    return result
```

- [ ] **Step 3: Write routes/sync_logs.py**

Create `src/api/routes/sync_logs.py`:

```python
# src/api/routes/sync_logs.py
"""同步日志查询 API 路由"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key, PaginationParams
from src.services import sync_task_service

router = APIRouter(dependencies=[Depends(get_current_api_key)])


@router.get("/sync-logs")
def list_sync_logs(
    params: PaginationParams = Depends(),
    connector_id: int | None = Query(None),
    entity: str | None = Query(None),
    status: str | None = Query(None),
    started_after: datetime | None = Query(None),
    started_before: datetime | None = Query(None),
    session: Session = Depends(get_db),
):
    result = sync_task_service.list_sync_logs(
        session, params,
        connector_id=connector_id,
        entity=entity,
        status=status,
        started_after=started_after,
        started_before=started_before,
    )
    result["items"] = [sync_task_service.sync_log_to_response(log) for log in result["items"]]
    return result
```

- [ ] **Step 4: Register sync routers in main.py**

Add to `src/main.py`:

```python
from src.api.routes.sync_tasks import router as sync_tasks_router
from src.api.routes.sync_logs import router as sync_logs_router
app.include_router(sync_tasks_router, prefix="/api/v1", tags=["sync"])
app.include_router(sync_logs_router, prefix="/api/v1", tags=["sync"])
```

- [ ] **Step 5: Write test_api_sync_tasks.py**

Create `tests/test_api_sync_tasks.py`:

```python
# tests/test_api_sync_tasks.py
"""同步任务管理 API 测试"""
import pytest
from src.models.connector import Connector


@pytest.fixture
def connector_in_db(db_session):
    """在 DB 中创建一个连接器供同步任务使用"""
    c = Connector(
        name="测试连接器",
        connector_type="kingdee_erp",
        base_url="https://erp.test.com",
        auth_config={"test": True},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


@pytest.fixture
def sample_task_data(connector_in_db):
    return {
        "connector_id": connector_in_db.id,
        "entity": "order",
        "direction": "pull",
        "cron_expression": "0 */2 * * *",
        "enabled": True,
    }


class TestCreateSyncTask:
    def test_create_success(self, client, api_headers, sample_task_data):
        resp = client.post("/api/v1/sync-tasks", json=sample_task_data, headers=api_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["entity"] == "order"
        assert data["direction"] == "pull"
        assert data["enabled"] is True
        assert "next_run_at" in data

    def test_create_without_cron(self, client, api_headers, connector_in_db):
        resp = client.post("/api/v1/sync-tasks", json={
            "connector_id": connector_in_db.id,
            "entity": "order",
            "direction": "pull",
        }, headers=api_headers)
        assert resp.status_code == 201
        assert resp.json()["cron_expression"] is None

    def test_create_invalid_connector(self, client, api_headers):
        resp = client.post("/api/v1/sync-tasks", json={
            "connector_id": 999,
            "entity": "order",
            "direction": "pull",
        }, headers=api_headers)
        assert resp.status_code == 400

    def test_create_invalid_direction(self, client, api_headers, connector_in_db):
        resp = client.post("/api/v1/sync-tasks", json={
            "connector_id": connector_in_db.id,
            "entity": "order",
            "direction": "invalid",
        }, headers=api_headers)
        assert resp.status_code == 422

    def test_create_requires_auth(self, client, sample_task_data):
        resp = client.post("/api/v1/sync-tasks", json=sample_task_data)
        assert resp.status_code == 401


class TestListSyncTasks:
    def test_list_empty(self, client, api_headers):
        resp = client.get("/api/v1/sync-tasks", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_list_with_data(self, client, api_headers, sample_task_data):
        client.post("/api/v1/sync-tasks", json=sample_task_data, headers=api_headers)
        resp = client.get("/api/v1/sync-tasks", headers=api_headers)
        assert resp.json()["total_count"] == 1


class TestUpdateSyncTask:
    def test_update_success(self, client, api_headers, sample_task_data):
        create_resp = client.post("/api/v1/sync-tasks", json=sample_task_data, headers=api_headers)
        tid = create_resp.json()["id"]
        resp = client.put(f"/api/v1/sync-tasks/{tid}", json={"enabled": False}, headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


class TestDeleteSyncTask:
    def test_delete_success(self, client, api_headers, sample_task_data):
        create_resp = client.post("/api/v1/sync-tasks", json=sample_task_data, headers=api_headers)
        tid = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/sync-tasks/{tid}", headers=api_headers)
        assert resp.status_code == 204
        # 验证已删除
        get_resp = client.get(f"/api/v1/sync-tasks/{tid}", headers=api_headers)
        assert get_resp.status_code == 404
```

- [ ] **Step 6: Write test_api_sync_logs.py**

Create `tests/test_api_sync_logs.py`:

```python
# tests/test_api_sync_logs.py
"""同步日志查询 API 测试"""
import pytest
from datetime import datetime, timezone
from src.models.connector import Connector
from src.models.sync import SyncLog


@pytest.fixture
def connector_in_db(db_session):
    c = Connector(
        name="日志测试连接器",
        connector_type="kingdee_erp",
        base_url="https://erp.test.com",
        auth_config={"test": True},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


@pytest.fixture
def sample_logs(db_session, connector_in_db):
    """创建几条同步日志"""
    logs = []
    for i, status in enumerate(["success", "failure", "success"]):
        log = SyncLog(
            connector_id=connector_in_db.id,
            entity="order",
            direction="pull",
            status=status,
            total_records=10,
            success_count=10 if status == "success" else 0,
            failure_count=0 if status == "success" else 10,
        )
        db_session.add(log)
        logs.append(log)
    db_session.flush()
    return logs


class TestListSyncLogs:
    def test_list_empty(self, client, api_headers):
        resp = client.get("/api/v1/sync-logs", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_list_with_data(self, client, api_headers, sample_logs):
        resp = client.get("/api/v1/sync-logs", headers=api_headers)
        assert resp.json()["total_count"] == 3

    def test_filter_by_status(self, client, api_headers, sample_logs):
        resp = client.get("/api/v1/sync-logs?status=failure", headers=api_headers)
        data = resp.json()
        assert data["total_count"] == 1
        assert data["items"][0]["status"] == "failure"

    def test_filter_by_connector_id(self, client, api_headers, sample_logs, connector_in_db):
        resp = client.get(f"/api/v1/sync-logs?connector_id={connector_in_db.id}", headers=api_headers)
        assert resp.json()["total_count"] == 3

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/sync-logs")
        assert resp.status_code == 401
```

- [ ] **Step 7: Run tests**

Run: `pytest -v`
Expected: All existing + ~15 new tests pass.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: 实现同步任务管理 API — CRUD + 手动触发 + 日志查询"
```

---

## Task 5: 数据回写 API (Push)

**Files:**
- Create: `src/services/push_service.py`
- Create: `src/api/routes/push.py`
- Create: `tests/test_api_push.py`
- Modify: `src/main.py` (add push router)

### Steps:

- [ ] **Step 1: Write push_service.py**

Create `src/services/push_service.py`:

```python
# src/services/push_service.py
"""数据推送服务：连接器实例化 + 连接管理 + 推送执行"""
import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.connectors.base import connector_registry, ConnectorError, PushResult
from src.core.config import get_settings
from src.core.security import decrypt_value
from src.models.connector import Connector


def execute_push(
    connector_type: str,
    entity: str,
    records: list[dict],
    session: Session,
) -> PushResult:
    """
    执行数据推送：
    1. 查 DB 找 enabled 的连接器
    2. 实例化连接器
    3. connect → push → disconnect
    """
    # 查找启用的连接器
    connector_model = (
        session.query(Connector)
        .filter_by(connector_type=connector_type, enabled=True)
        .first()
    )
    if not connector_model:
        raise HTTPException(
            status_code=404,
            detail=f"No enabled connector found for type: {connector_type}",
        )

    # 实例化连接器
    connector_class = connector_registry.get(connector_type)
    auth_config = connector_model.auth_config

    # 解密凭证
    settings = get_settings()
    if isinstance(auth_config, dict) and "_encrypted" in auth_config:
        decrypted = decrypt_value(auth_config["_encrypted"], settings.ENCRYPTION_KEY)
        auth_config = json.loads(decrypted)

    config = {
        "base_url": connector_model.base_url,
        "auth_config": auth_config,
    }
    connector = connector_class(config)

    try:
        connector.connect()
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=f"Connector unavailable: {str(e)}")

    try:
        result = connector.push(entity, records)
        return result
    except ConnectorError as e:
        raise HTTPException(status_code=502, detail=f"Push failed: {str(e)}")
    finally:
        try:
            connector.disconnect()
        except Exception:
            pass
```

- [ ] **Step 2: Write routes/push.py**

Create `src/api/routes/push.py`:

```python
# src/api/routes/push.py
"""数据回写 API 路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key
from src.api.schemas.data import PushRequest, PushResponse
from src.services import push_service

router = APIRouter(dependencies=[Depends(get_current_api_key)])


@router.post("/push/{connector_type}/{entity}")
def push_data(
    connector_type: str,
    entity: str,
    data: PushRequest,
    session: Session = Depends(get_db),
) -> PushResponse:
    result = push_service.execute_push(connector_type, entity, data.records, session)
    return PushResponse(
        success_count=result.success_count,
        failure_count=result.failure_count,
        failures=result.failures,
    )
```

- [ ] **Step 3: Register push router in main.py**

Add to `src/main.py`:

```python
from src.api.routes.push import router as push_router
app.include_router(push_router, prefix="/api/v1", tags=["push"])
```

- [ ] **Step 4: Write test_api_push.py**

Create `tests/test_api_push.py`:

```python
# tests/test_api_push.py
"""数据回写 API 测试"""
import pytest
from unittest.mock import patch, MagicMock
from src.models.connector import Connector
from src.connectors.base import PushResult, ConnectorError


@pytest.fixture
def connector_in_db(db_session):
    c = Connector(
        name="推送测试连接器",
        connector_type="kingdee_erp",
        base_url="https://erp.test.com",
        auth_config={"test": True},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


class TestPushData:
    def test_push_success(self, client, api_headers, connector_in_db):
        mock_connector = MagicMock()
        mock_connector.push.return_value = PushResult(success_count=2, failure_count=0, failures=[])
        mock_class = MagicMock(return_value=mock_connector)

        with patch("src.services.push_service.connector_registry") as mock_registry:
            mock_registry.get.return_value = mock_class
            resp = client.post(
                "/api/v1/push/kingdee_erp/order",
                json={"records": [{"name": "A"}, {"name": "B"}]},
                headers=api_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success_count"] == 2
        assert data["failure_count"] == 0

    def test_push_no_connector(self, client, api_headers):
        resp = client.post(
            "/api/v1/push/nonexistent/order",
            json={"records": [{"name": "A"}]},
            headers=api_headers,
        )
        assert resp.status_code == 404

    def test_push_connector_unavailable(self, client, api_headers, connector_in_db):
        mock_connector = MagicMock()
        mock_connector.connect.side_effect = ConnectorError("Connection refused")
        mock_class = MagicMock(return_value=mock_connector)

        with patch("src.services.push_service.connector_registry") as mock_registry:
            mock_registry.get.return_value = mock_class
            resp = client.post(
                "/api/v1/push/kingdee_erp/order",
                json={"records": [{"name": "A"}]},
                headers=api_headers,
            )
        assert resp.status_code == 502

    def test_push_empty_records(self, client, api_headers, connector_in_db):
        resp = client.post(
            "/api/v1/push/kingdee_erp/order",
            json={"records": []},
            headers=api_headers,
        )
        assert resp.status_code == 422  # min_length=1 validation

    def test_push_partial_failure(self, client, api_headers, connector_in_db):
        mock_connector = MagicMock()
        mock_connector.push.return_value = PushResult(
            success_count=1, failure_count=1,
            failures=[{"record": {"name": "B"}, "error": "failed"}],
        )
        mock_class = MagicMock(return_value=mock_connector)

        with patch("src.services.push_service.connector_registry") as mock_registry:
            mock_registry.get.return_value = mock_class
            resp = client.post(
                "/api/v1/push/kingdee_erp/order",
                json={"records": [{"name": "A"}, {"name": "B"}]},
                headers=api_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success_count"] == 1
        assert data["failure_count"] == 1
        assert len(data["failures"]) == 1

    def test_push_requires_auth(self, client):
        resp = client.post("/api/v1/push/kingdee_erp/order", json={"records": [{"name": "A"}]})
        assert resp.status_code == 401
```

- [ ] **Step 5: Run tests**

Run: `pytest -v`
Expected: All existing + ~6 new tests pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: 实现数据回写 API — push 端点 + 连接器实例化"
```

---

## Task 6: 数据查询 API (Unified + Raw Data)

**Files:**
- Create: `src/api/routes/data.py`
- Create: `tests/test_api_data.py`
- Modify: `src/main.py` (add data router)

### Steps:

- [ ] **Step 1: Write routes/data.py**

Create `src/api/routes/data.py`:

```python
# src/api/routes/data.py
"""统一数据 + 原始数据查询 API 路由"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key, PaginationParams, paginate
from src.models.connector import Connector
from src.models.raw_data import RawData
from src.models.unified import (
    UnifiedCustomer, UnifiedOrder, UnifiedProduct,
    UnifiedInventory, UnifiedProject, UnifiedContact,
)

router = APIRouter(dependencies=[Depends(get_current_api_key)])

# 实体路由映射
ENTITY_REGISTRY: dict[str, type] = {
    "customers": UnifiedCustomer,
    "orders": UnifiedOrder,
    "products": UnifiedProduct,
    "inventory": UnifiedInventory,
    "projects": UnifiedProject,
    "contacts": UnifiedContact,
}

# 分页/排序相关的保留参数名，不当作过滤条件
RESERVED_PARAMS = {"page", "page_size", "sort_by", "sort_order"}


def _get_model(entity: str):
    model = ENTITY_REGISTRY.get(entity)
    if not model:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown entity: {entity}. Valid: {list(ENTITY_REGISTRY.keys())}",
        )
    return model


@router.get("/data/{entity}")
def list_unified_data(
    entity: str,
    request: Request,
    params: PaginationParams = Depends(),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    session: Session = Depends(get_db),
):
    model = _get_model(entity)
    query = session.query(model)

    # 动态过滤
    valid_columns = {c.name for c in model.__table__.columns}
    for key, value in request.query_params.items():
        if key in RESERVED_PARAMS:
            continue
        if key not in valid_columns:
            raise HTTPException(status_code=400, detail=f"Invalid filter column: {key}")
        query = query.filter(getattr(model, key) == value)

    # 排序
    if sort_by not in valid_columns:
        raise HTTPException(status_code=400, detail=f"Invalid sort column: {sort_by}")
    order_col = getattr(model, sort_by)
    query = query.order_by(order_col.desc() if sort_order == "desc" else order_col.asc())

    result = paginate(query, params)
    # 将 ORM 对象序列化为字典
    result["items"] = [
        {c.name: getattr(row, c.name) for c in model.__table__.columns}
        for row in result["items"]
    ]
    return result


@router.get("/data/{entity}/{record_id}")
def get_unified_record(
    entity: str,
    record_id: int,
    session: Session = Depends(get_db),
):
    model = _get_model(entity)
    record = session.query(model).filter_by(id=record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"{entity} record with id {record_id} not found")
    return {c.name: getattr(record, c.name) for c in model.__table__.columns}


@router.get("/raw/{connector_type}/{entity}")
def list_raw_data(
    connector_type: str,
    entity: str,
    params: PaginationParams = Depends(),
    session: Session = Depends(get_db),
):
    # 查找匹配 connector_type 的所有 connector_id
    connector_ids = [
        c.id for c in
        session.query(Connector.id).filter_by(connector_type=connector_type).all()
    ]
    if not connector_ids:
        raise HTTPException(status_code=404, detail=f"No connectors found for type: {connector_type}")

    query = (
        session.query(RawData)
        .filter(RawData.connector_id.in_(connector_ids))
        .filter(RawData.entity == entity)
        .order_by(RawData.synced_at.desc())
    )
    result = paginate(query, params)
    result["items"] = [
        {
            "id": row.id,
            "connector_id": row.connector_id,
            "entity": row.entity,
            "external_id": row.external_id,
            "data": row.data,
            "synced_at": row.synced_at,
        }
        for row in result["items"]
    ]
    return result
```

- [ ] **Step 2: Register data router in main.py**

Add to `src/main.py`:

```python
from src.api.routes.data import router as data_router
app.include_router(data_router, prefix="/api/v1", tags=["data"])
```

- [ ] **Step 3: Write test_api_data.py**

Create `tests/test_api_data.py`:

```python
# tests/test_api_data.py
"""统一数据 + 原始数据查询 API 测试"""
import pytest
from src.models.unified import UnifiedCustomer, UnifiedOrder
from src.models.connector import Connector
from src.models.raw_data import RawData


@pytest.fixture
def sample_customers(db_session):
    """创建测试客户数据"""
    customers = []
    for i in range(3):
        c = UnifiedCustomer(
            name=f"客户{i}",
            source_system="fenxiangxiaoke",
            external_id=f"ext_{i}",
            status="active" if i < 2 else "inactive",
        )
        db_session.add(c)
        customers.append(c)
    db_session.flush()
    return customers


@pytest.fixture
def raw_data_in_db(db_session):
    """创建原始数据"""
    c = Connector(
        name="原始数据测试连接器",
        connector_type="kingdee_erp",
        base_url="https://erp.test.com",
        auth_config={},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    for i in range(2):
        rd = RawData(
            connector_id=c.id,
            entity="sales_order",
            external_id=f"SO{i}",
            data={"FBillNo": f"SO{i}", "amount": 100 * i},
        )
        db_session.add(rd)
    db_session.flush()
    return c


class TestListUnifiedData:
    def test_list_customers(self, client, api_headers, sample_customers):
        resp = client.get("/api/v1/data/customers", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3

    def test_list_with_filter(self, client, api_headers, sample_customers):
        resp = client.get("/api/v1/data/customers?status=active", headers=api_headers)
        data = resp.json()
        assert data["total_count"] == 2

    def test_list_invalid_entity(self, client, api_headers):
        resp = client.get("/api/v1/data/unknown", headers=api_headers)
        assert resp.status_code == 404

    def test_list_invalid_filter_column(self, client, api_headers, sample_customers):
        resp = client.get("/api/v1/data/customers?nonexistent=value", headers=api_headers)
        assert resp.status_code == 400

    def test_list_with_sorting(self, client, api_headers, sample_customers):
        resp = client.get("/api/v1/data/customers?sort_by=name&sort_order=asc", headers=api_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        names = [item["name"] for item in items]
        assert names == sorted(names)

    def test_list_with_pagination(self, client, api_headers, sample_customers):
        resp = client.get("/api/v1/data/customers?page=1&page_size=2", headers=api_headers)
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total_count"] == 3


class TestGetUnifiedRecord:
    def test_get_success(self, client, api_headers, sample_customers):
        cid = sample_customers[0].id
        resp = client.get(f"/api/v1/data/customers/{cid}", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "客户0"

    def test_get_not_found(self, client, api_headers):
        resp = client.get("/api/v1/data/customers/999", headers=api_headers)
        assert resp.status_code == 404


class TestListRawData:
    def test_list_raw(self, client, api_headers, raw_data_in_db):
        resp = client.get("/api/v1/raw/kingdee_erp/sales_order", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert "data" in data["items"][0]

    def test_raw_no_connector(self, client, api_headers):
        resp = client.get("/api/v1/raw/nonexistent/order", headers=api_headers)
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/data/customers")
        assert resp.status_code == 401
```

- [ ] **Step 4: Run tests**

Run: `pytest -v`
Expected: All existing + ~11 new tests pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: 实现数据查询 API — 统一数据 + 原始数据 + 过滤排序"
```

---

## Task 7: 健康检查增强 + main.py 最终化

**Files:**
- Modify: `src/api/routes/health.py` (enhance with real DB check)
- Modify: `tests/test_api_health.py` (add component-level tests)

### Steps:

- [ ] **Step 1: Enhance routes/health.py**

Rewrite `src/api/routes/health.py`:

```python
# src/api/routes/health.py
"""增强版健康检查端点"""
import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.deps import get_db

router = APIRouter()


@router.get("/health")
def health_check(session: Session = Depends(get_db)):
    """
    平台健康检查 — 免认证。
    检查: database, redis (not_configured), celery (not_configured)
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

    # Redis — 当前未配置
    components["redis"] = {"status": "not_configured"}

    # Celery — 当前未配置
    components["celery"] = {"status": "not_configured"}

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

- [ ] **Step 2: Enhance test_api_health.py with component-level tests**

Replace `tests/test_api_health.py` (previously rewritten in Task 1) with full component tests:

```python
# tests/test_api_health.py
"""增强版健康检查 API 测试"""


def test_root(client):
    """根路径应返回应用信息"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "数据中台"


def test_health_returns_status(client):
    """健康检查应返回 overall status"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded", "unhealthy")


def test_health_has_components(client):
    """健康检查应包含所有组件状态"""
    resp = client.get("/api/v1/health")
    data = resp.json()
    assert "database" in data["components"]
    assert "redis" in data["components"]
    assert "celery" in data["components"]


def test_health_database_latency(client):
    """数据库健康检查应返回延迟"""
    resp = client.get("/api/v1/health")
    db = resp.json()["components"]["database"]
    assert db["status"] == "healthy"
    assert "latency_ms" in db


def test_health_no_auth_required(client):
    """健康检查端点不需要认证"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_health_has_version(client):
    """健康检查应返回版本号"""
    resp = client.get("/api/v1/health")
    assert resp.json()["version"] == "0.1.0"


def test_health_redis_not_configured(client):
    """Redis 当前应为 not_configured"""
    resp = client.get("/api/v1/health")
    assert resp.json()["components"]["redis"]["status"] == "not_configured"
```

- [ ] **Step 3: Delete old src/api/health.py if still present**

Verify `src/api/health.py` was deleted in Task 1. If not, delete it now.

- [ ] **Step 4: Run tests**

Run: `pytest -v`
Expected: All tests pass, including updated health tests.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: 增强健康检查 — DB 延迟检测 + 组件状态 + 版本号"
```

---

## Task 8: 完善认证测试 + 错误格式测试 + 最终验证

**Files:**
- Modify: `tests/test_api_deps.py` (now we have auth-protected endpoints)
- Modify: `tests/test_api_errors.py` (now we can trigger validation errors)

### Steps:

- [ ] **Step 1: Enhance test_api_deps.py with real auth tests**

Update `tests/test_api_deps.py` to use connector endpoints (which require auth):

```python
# tests/test_api_deps.py
"""API 认证和分页依赖测试"""


class TestAPIKeyAuth:
    def test_valid_bearer_token(self, client, api_headers):
        """有效 Bearer token 应通过认证"""
        resp = client.get("/api/v1/connectors", headers=api_headers)
        assert resp.status_code == 200

    def test_valid_x_api_key(self, client):
        """有效 X-API-Key 头应通过认证"""
        resp = client.get("/api/v1/connectors", headers={"X-API-Key": "test-api-key"})
        assert resp.status_code == 200

    def test_missing_api_key_returns_401(self, client):
        """缺少 API Key 应返回 401"""
        resp = client.get("/api/v1/connectors")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "UNAUTHORIZED"

    def test_invalid_bearer_token_returns_401(self, client):
        """无效 Bearer token 应返回 401"""
        resp = client.get("/api/v1/connectors", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    def test_health_no_auth_required(self, client):
        """健康检查免认证"""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200


class TestPaginationParams:
    def test_pagination_defaults(self):
        from src.api.deps import PaginationParams
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 20
        assert params.offset == 0

    def test_pagination_offset_calculation(self):
        from src.api.deps import PaginationParams
        params = PaginationParams(page=3, page_size=10)
        assert params.offset == 20
```

- [ ] **Step 2: Enhance test_api_errors.py**

Update `tests/test_api_errors.py`:

```python
# tests/test_api_errors.py
"""统一错误响应格式测试"""


def test_401_error_format(client):
    """401 应返回标准错误格式"""
    resp = client.get("/api/v1/connectors")
    assert resp.status_code == 401
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "message" in data["error"]


def test_404_error_format(client, api_headers):
    """404 应返回标准错误格式"""
    resp = client.get("/api/v1/connectors/999", headers=api_headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


def test_422_validation_error_format(client, api_headers):
    """422 验证错误应包含 details"""
    resp = client.post("/api/v1/connectors", json={}, headers=api_headers)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["details"] is not None


def test_error_response_has_consistent_structure(client, api_headers):
    """所有错误响应都应有 error.code, error.message, error.details"""
    resp = client.get("/api/v1/data/unknown_entity", headers=api_headers)
    data = resp.json()
    assert "error" in data
    error = data["error"]
    assert "code" in error
    assert "message" in error
    assert "details" in error
```

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests pass. Count should be approximately 100 (existing) + 54 (new) = ~154 tests.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: 完善认证测试和错误格式测试"
```

- [ ] **Step 5: Final verification — run full test suite one more time**

Run: `pytest -v --tb=short`
Expected: All tests pass, clean output.

---

## Summary

| Task | Description | Est. New Tests |
|------|-------------|----------------|
| 1 | 基础设施层 (deps, errors, schemas/common, conftest, main.py, health test rewrite) | ~9 |
| 2 | Pydantic Schemas (connector, sync, data) | 0 |
| 3 | 连接器管理 API (CRUD + soft-delete) | ~11 |
| 4 | 同步任务管理 API (CRUD + trigger + logs) | ~15 |
| 5 | 数据回写 API (push) | ~6 |
| 6 | 数据查询 API (unified + raw) | ~11 |
| 7 | 健康检查增强 | ~4 (replace Task 1 stubs) |
| 8 | 认证/错误测试完善 | ~11 |
| **Total** | | **~69 new tests** |

Final state: ~169 total tests (100 existing + ~69 new), full REST API for the data platform.
