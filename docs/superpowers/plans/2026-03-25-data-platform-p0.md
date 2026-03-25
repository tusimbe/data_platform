# 企业数据中台 P0 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建数据中台基础平台，实现连接器框架、金蝶ERP连接器、双层数据模型，使系统能够从金蝶ERP拉取数据并存储到 PostgreSQL。

**Architecture:** FastAPI 单体分层架构，SQLAlchemy 2.0 ORM + Alembic 数据库迁移，Celery + Redis 任务队列。连接器通过抽象基类统一接口，数据采用原始层（JSONB）+ 统一层（结构化表）双层存储。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, Celery, Redis, PostgreSQL, pytest, httpx, Docker Compose

**Spec:** `docs/superpowers/specs/2026-03-25-data-platform-design.md` + `openspec/specs/` 下四个行为规范

---

## 文件结构

### 新建文件

| 文件路径 | 职责 |
|----------|------|
| `pyproject.toml` | 项目元数据、依赖、工具配置 |
| `docker-compose.yml` | 本地开发环境（PostgreSQL + Redis） |
| `src/__init__.py` | 包初始化 |
| `src/main.py` | FastAPI 应用入口 |
| `src/core/__init__.py` | 核心模块 |
| `src/core/config.py` | Pydantic Settings 配置管理 |
| `src/core/database.py` | SQLAlchemy 引擎和会话管理 |
| `src/core/security.py` | 凭据加密工具 |
| `src/models/__init__.py` | 模型包，导出所有模型 |
| `src/models/base.py` | SQLAlchemy 声明式基类 + 通用 Mixin |
| `src/models/connector.py` | Connector 配置模型 |
| `src/models/sync.py` | SyncTask + SyncLog 模型 |
| `src/models/raw_data.py` | RawData 原始数据模型 |
| `src/models/unified.py` | 6 张统一模型表 |
| `src/models/field_mapping.py` | FieldMapping + EntitySchema 模型 |
| `src/connectors/__init__.py` | 连接器包，导出注册表 |
| `src/connectors/base.py` | BaseConnector 抽象基类 + 注册器 + 数据类型 |
| `src/connectors/kingdee_erp.py` | 金蝶ERP连接器实现 |
| `src/services/__init__.py` | 服务包 |
| `src/services/sync_service.py` | 同步执行服务（拉取流程三阶段） |
| `src/services/field_mapping_service.py` | 字段映射转换服务 |
| `src/api/__init__.py` | API 包 |
| `src/api/health.py` | 健康检查路由 |
| `alembic.ini` | Alembic 配置 |
| `alembic/env.py` | Alembic 环境配置 |
| `alembic/versions/` | 迁移脚本目录 |
| `tests/__init__.py` | 测试包 |
| `tests/conftest.py` | pytest fixtures（测试数据库、客户端） |
| `tests/test_config.py` | 配置管理测试 |
| `tests/test_connector_base.py` | 连接器基类 + 注册表测试 |
| `tests/test_connector_kingdee.py` | 金蝶ERP连接器测试 |
| `tests/test_models.py` | 数据模型测试 |
| `tests/test_field_mapping.py` | 字段映射服务测试 |
| `tests/test_sync_service.py` | 同步服务测试 |
| `tests/test_api_health.py` | 健康检查 API 测试 |

---

## Task 1: 项目脚手架

**Files:**
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `src/__init__.py`
- Create: `src/main.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "data-platform"
version = "0.1.0"
description = "企业数据中台"
requires-python = ">=3.11"
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
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
    "ruff>=0.5.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: 创建 docker-compose.yml**

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

volumes:
  pgdata:
```

- [ ] **Step 3: 创建 src/__init__.py（空文件）和 tests/__init__.py（空文件）**

- [ ] **Step 4: 创建 src/main.py（最小 FastAPI 应用）**

```python
from fastapi import FastAPI

app = FastAPI(title="数据中台", version="0.1.0")


@app.get("/")
def root():
    return {"name": "数据中台", "version": "0.1.0"}
```

- [ ] **Step 5: 安装依赖并验证**

Run: `cd data_platform && pip install -e ".[dev]"`
Expected: 依赖安装成功

Run: `cd data_platform && python -c "from src.main import app; print(app.title)"`
Expected: `数据中台`

- [ ] **Step 6: 启动 Docker 服务**

Run: `cd data_platform && docker compose up -d`
Expected: PostgreSQL 和 Redis 容器启动

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "feat: 初始化项目脚手架

添加 pyproject.toml、docker-compose.yml、FastAPI 入口，
配置 PostgreSQL + Redis 本地开发环境。"
```

---

## Task 2: 配置管理

**Files:**
- Create: `src/core/__init__.py`
- Create: `src/core/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: 编写配置管理测试**

```python
# tests/test_config.py
import os
from unittest.mock import patch


def test_default_config():
    """默认配置应有合理的默认值"""
    from src.core.config import Settings

    settings = Settings(
        DATABASE_URL="postgresql://u:p@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
    )
    assert settings.APP_NAME == "数据中台"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.DATABASE_URL == "postgresql://u:p@localhost/db"


def test_config_from_env():
    """配置应支持从环境变量读取"""
    with patch.dict(os.environ, {
        "DATABASE_URL": "postgresql://test:test@db/test",
        "REDIS_URL": "redis://redis:6379/0",
        "APP_NAME": "测试中台",
    }):
        from importlib import reload
        import src.core.config as config_mod
        reload(config_mod)
        settings = config_mod.Settings()
        assert settings.APP_NAME == "测试中台"
        assert settings.DATABASE_URL == "postgresql://test:test@db/test"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_config.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现配置管理**

```python
# src/core/__init__.py
（空文件）

# src/core/config.py
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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd data_platform && python -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 添加 Pydantic Settings 配置管理

支持环境变量和 .env 文件读取数据库、Redis、API 配置。"
```

---

## Task 3: 数据库连接与基础模型

**Files:**
- Create: `src/core/database.py`
- Create: `src/models/__init__.py`
- Create: `src/models/base.py`
- Test: `tests/conftest.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 编写数据库连接和基础模型测试**

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.base import Base


@pytest.fixture(scope="session")
def engine():
    """使用 SQLite 内存数据库做测试"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(engine):
    """每个测试一个独立事务，测试后回滚"""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
```

```python
# tests/test_models.py
from src.models.base import Base


def test_base_model_exists():
    """声明式基类应存在且可用"""
    assert Base is not None
    assert hasattr(Base, "metadata")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_models.py -v`
Expected: FAIL

- [ ] **Step 3: 实现数据库连接和基础模型**

```python
# src/core/database.py
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
```

```python
# src/models/__init__.py
from src.models.base import Base  # noqa: F401

# src/models/base.py
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """通用时间戳字段"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd data_platform && python -m pytest tests/test_models.py tests/conftest.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 添加数据库连接管理和 SQLAlchemy 声明式基类

包含 TimestampMixin 通用时间戳，SQLite 内存测试 fixtures。"
```

---

## Task 4: 平台元数据模型（connectors, sync_tasks, sync_logs）

**Files:**
- Create: `src/models/connector.py`
- Create: `src/models/sync.py`
- Modify: `src/models/__init__.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: 编写元数据模型测试**

```python
# tests/test_models.py — 追加以下测试

from src.models.connector import Connector
from src.models.sync import SyncTask, SyncLog


def test_create_connector(db_session):
    """应能创建连接器配置记录"""
    c = Connector(
        name="测试金蝶ERP",
        connector_type="kingdee_erp",
        base_url="https://api.kingdee.com",
        auth_config={"app_id": "xxx", "app_secret": "yyy"},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    assert c.id is not None
    assert c.connector_type == "kingdee_erp"
    assert c.enabled is True


def test_create_sync_task(db_session):
    """应能创建同步任务"""
    c = Connector(
        name="测试", connector_type="test", base_url="http://test",
        auth_config={}, enabled=True,
    )
    db_session.add(c)
    db_session.flush()

    task = SyncTask(
        connector_id=c.id,
        entity="sales_order",
        direction="pull",
        cron_expression="0 */2 * * *",
        enabled=True,
    )
    db_session.add(task)
    db_session.flush()
    assert task.id is not None
    assert task.direction == "pull"


def test_create_sync_log(db_session):
    """应能创建同步日志"""
    c = Connector(
        name="测试", connector_type="test", base_url="http://test",
        auth_config={}, enabled=True,
    )
    db_session.add(c)
    db_session.flush()

    task = SyncTask(
        connector_id=c.id, entity="order", direction="pull",
        cron_expression="0 * * * *", enabled=True,
    )
    db_session.add(task)
    db_session.flush()

    log = SyncLog(
        sync_task_id=task.id,
        connector_id=c.id,
        entity="order",
        direction="pull",
        status="success",
        total_records=100,
        success_count=98,
        failure_count=2,
        error_details={"failed_ids": ["001", "002"]},
    )
    db_session.add(log)
    db_session.flush()
    assert log.id is not None
    assert log.status == "success"
    assert log.failure_count == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_models.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现元数据模型**

```python
# src/models/connector.py
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

# 兼容 SQLite 测试和 PostgreSQL 生产
try:
    from sqlalchemy.dialects.postgresql import JSONB as JSONType
except ImportError:
    JSONType = SQLiteJSON


class Connector(Base, TimestampMixin):
    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    auth_config: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    sync_tasks = relationship("SyncTask", back_populates="connector")
    sync_logs = relationship("SyncLog", back_populates="connector")
```

```python
# src/models/sync.py
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

try:
    from sqlalchemy.dialects.postgresql import JSONB as JSONType
except ImportError:
    JSONType = SQLiteJSON


class SyncTask(Base, TimestampMixin):
    __tablename__ = "sync_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "pull" | "push"
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    connector = relationship("Connector", back_populates="sync_tasks")
    sync_logs = relationship("SyncLog", back_populates="sync_task")


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_task_id: Mapped[int] = mapped_column(ForeignKey("sync_tasks.id"), nullable=False)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success/partial_success/failure
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    error_details: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sync_task = relationship("SyncTask", back_populates="sync_logs")
    connector = relationship("Connector", back_populates="sync_logs")
```

更新 `src/models/__init__.py`:

```python
from src.models.base import Base  # noqa: F401
from src.models.connector import Connector  # noqa: F401
from src.models.sync import SyncTask, SyncLog  # noqa: F401
```

更新 `tests/conftest.py` 确保 import 所有模型使得 metadata.create_all 能建表:

```python
# tests/conftest.py — 顶部追加
import src.models  # noqa: F401 — 确保所有模型都注册到 Base.metadata
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd data_platform && python -m pytest tests/test_models.py -v`
Expected: 4 passed（含之前的 test_base_model_exists）

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 添加 Connector, SyncTask, SyncLog 元数据模型

支持连接器配置持久化、同步任务定义和同步执行日志记录。"
```

---

## Task 5: 原始数据模型 + 统一业务模型

**Files:**
- Create: `src/models/raw_data.py`
- Create: `src/models/unified.py`
- Create: `src/models/field_mapping.py`
- Modify: `src/models/__init__.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: 编写原始数据和统一模型测试**

```python
# tests/test_models.py — 追加以下测试

from src.models.raw_data import RawData
from src.models.unified import (
    UnifiedCustomer, UnifiedOrder, UnifiedProduct,
    UnifiedInventory, UnifiedProject, UnifiedContact,
)
from src.models.field_mapping import FieldMapping, EntitySchema


def test_create_raw_data(db_session):
    """应能存储原始 JSONB 数据"""
    c = Connector(
        name="测试", connector_type="test", base_url="http://test",
        auth_config={}, enabled=True,
    )
    db_session.add(c)
    db_session.flush()

    raw = RawData(
        connector_id=c.id,
        entity="sales_order",
        external_id="SO-001",
        data={"FBillNo": "SO-001", "FAmount": 1000.00},
    )
    db_session.add(raw)
    db_session.flush()
    assert raw.id is not None
    assert raw.data["FBillNo"] == "SO-001"


def test_create_unified_customer(db_session):
    """应能创建统一客户记录"""
    customer = UnifiedCustomer(
        source_system="fenxiangxiaoke",
        external_id="C-001",
        name="测试公司",
        company="测试有限公司",
        phone="13800138000",
        email="test@example.com",
    )
    db_session.add(customer)
    db_session.flush()
    assert customer.id is not None
    assert customer.source_system == "fenxiangxiaoke"


def test_create_unified_order(db_session):
    """应能创建统一订单记录"""
    order = UnifiedOrder(
        source_system="kingdee_erp",
        external_id="SO-001",
        order_number="SO-001",
        order_type="sales",
        total_amount=1000.00,
        currency="CNY",
        status="approved",
    )
    db_session.add(order)
    db_session.flush()
    assert order.id is not None


def test_create_field_mapping(db_session):
    """应能创建字段映射记录"""
    mapping = FieldMapping(
        connector_type="kingdee_erp",
        source_entity="sales_order",
        target_table="unified_orders",
        source_field="FBillNo",
        target_field="order_number",
    )
    db_session.add(mapping)
    db_session.flush()
    assert mapping.id is not None


def test_unified_tables_have_source_traceability():
    """所有统一表应包含溯源字段"""
    for model in [UnifiedCustomer, UnifiedOrder, UnifiedProduct,
                  UnifiedInventory, UnifiedProject, UnifiedContact]:
        columns = {c.name for c in model.__table__.columns}
        assert "source_system" in columns, f"{model.__name__} missing source_system"
        assert "external_id" in columns, f"{model.__name__} missing external_id"
        assert "source_data_id" in columns, f"{model.__name__} missing source_data_id"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_models.py::test_create_raw_data -v`
Expected: FAIL

- [ ] **Step 3: 实现 RawData 模型**

```python
# src/models/raw_data.py
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

try:
    from sqlalchemy.dialects.postgresql import JSONB as JSONType
except ImportError:
    JSONType = SQLiteJSON


class RawData(Base):
    __tablename__ = "raw_data"
    __table_args__ = (
        UniqueConstraint("connector_id", "entity", "external_id", name="uq_raw_data_source"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sync_log_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sync_logs.id"), nullable=True
    )
```

- [ ] **Step 4: 实现统一模型（6张表）**

```python
# src/models/unified.py
from datetime import datetime, date

from sqlalchemy import (
    BigInteger, Date, DateTime, Integer, Numeric, String, Text, ForeignKey, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class _UnifiedMixin(TimestampMixin):
    """所有统一表共享的溯源字段"""
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_data_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UnifiedCustomer(Base, _UnifiedMixin):
    __tablename__ = "unified_customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)


class UnifiedOrder(Base, _UnifiedMixin):
    __tablename__ = "unified_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(100), nullable=False)
    order_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # sales/purchase
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class UnifiedProduct(Base, _UnifiedMixin):
    __tablename__ = "unified_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)


class UnifiedInventory(Base, _UnifiedMixin):
    __tablename__ = "unified_inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warehouse: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    available_quantity: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)


class UnifiedProject(Base, _UnifiedMixin):
    __tablename__ = "unified_projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)


class UnifiedContact(Base, _UnifiedMixin):
    __tablename__ = "unified_contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

- [ ] **Step 5: 实现 FieldMapping 和 EntitySchema 模型**

```python
# src/models/field_mapping.py
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin

try:
    from sqlalchemy.dialects.postgresql import JSONB as JSONType
except ImportError:
    JSONType = SQLiteJSON


class FieldMapping(Base, TimestampMixin):
    __tablename__ = "field_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(100), nullable=False)
    target_table: Mapped[str] = mapped_column(String(100), nullable=False)
    source_field: Mapped[str] = mapped_column(String(100), nullable=False)
    target_field: Mapped[str] = mapped_column(String(100), nullable=False)
    transform: Mapped[str | None] = mapped_column(String(50), nullable=True)  # date_format/value_map/concat/split
    transform_config: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class EntitySchema(Base, TimestampMixin):
    __tablename__ = "entity_schemas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_data: Mapped[dict] = mapped_column(JSONType, nullable=False)
```

更新 `src/models/__init__.py`:

```python
from src.models.base import Base  # noqa: F401
from src.models.connector import Connector  # noqa: F401
from src.models.sync import SyncTask, SyncLog  # noqa: F401
from src.models.raw_data import RawData  # noqa: F401
from src.models.unified import (  # noqa: F401
    UnifiedCustomer, UnifiedOrder, UnifiedProduct,
    UnifiedInventory, UnifiedProject, UnifiedContact,
)
from src.models.field_mapping import FieldMapping, EntitySchema  # noqa: F401
```

- [ ] **Step 6: 运行全部模型测试**

Run: `cd data_platform && python -m pytest tests/test_models.py -v`
Expected: 全部通过（约 9 个测试）

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "feat: 添加 RawData 原始数据、6张统一模型表、FieldMapping 字段映射

实现双层存储：原始层（JSONB）+ 统一层（结构化表），
包含 unified_customers/orders/products/inventory/projects/contacts。"
```

---

## Task 6: 连接器抽象基类与注册表

**Files:**
- Create: `src/connectors/__init__.py`
- Create: `src/connectors/base.py`
- Test: `tests/test_connector_base.py`

- [ ] **Step 1: 编写连接器基类和注册表测试**

```python
# tests/test_connector_base.py
import pytest
from datetime import datetime

from src.connectors.base import (
    BaseConnector, ConnectorRegistry, register_connector,
    HealthStatus, EntityInfo, PushResult,
    ConnectorNotFoundError, ConnectorPullError, ConnectorError,
)


def test_base_connector_is_abstract():
    """BaseConnector 不能直接实例化"""
    with pytest.raises(TypeError):
        BaseConnector(config={})


def test_register_and_lookup_connector():
    """注册器应能注册和查找连接器"""
    registry = ConnectorRegistry()

    @registry.register("test_system")
    class TestConnector(BaseConnector):
        def connect(self): pass
        def disconnect(self): pass
        def health_check(self): return HealthStatus(status="healthy", latency_ms=10)
        def list_entities(self): return []
        def pull(self, entity, since=None, filters=None): return []
        def push(self, entity, records): return PushResult(success_count=0, failure_count=0)
        def get_schema(self, entity): return {}

    cls = registry.get("test_system")
    assert cls is TestConnector


def test_lookup_unknown_connector():
    """查找未注册的连接器应抛出 ConnectorNotFoundError"""
    registry = ConnectorRegistry()
    with pytest.raises(ConnectorNotFoundError):
        registry.get("nonexistent")


def test_health_status_dataclass():
    """HealthStatus 数据类应正常工作"""
    h = HealthStatus(status="healthy", latency_ms=42)
    assert h.status == "healthy"
    assert h.latency_ms == 42

    h2 = HealthStatus(status="unhealthy", error="connection refused")
    assert h2.error == "connection refused"


def test_push_result_dataclass():
    """PushResult 数据类应正常工作"""
    r = PushResult(success_count=8, failure_count=2, failures=[{"id": "1", "error": "invalid"}])
    assert r.success_count == 8
    assert len(r.failures) == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_connector_base.py -v`
Expected: FAIL

- [ ] **Step 3: 实现连接器基类和注册表**

```python
# src/connectors/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


# --- 异常类 ---

class ConnectorError(Exception):
    """连接器通用异常"""
    pass


class ConnectorNotFoundError(ConnectorError):
    """连接器类型未注册"""
    pass


class ConnectorPullError(ConnectorError):
    """数据拉取失败"""
    pass


class ConnectorPushError(ConnectorError):
    """数据推送失败"""
    pass


# --- 数据类型 ---

@dataclass
class HealthStatus:
    status: str  # "healthy" | "unhealthy"
    latency_ms: float | None = None
    error: str | None = None


@dataclass
class EntityInfo:
    name: str
    description: str = ""
    supports_incremental: bool = True


@dataclass
class PushResult:
    success_count: int
    failure_count: int
    failures: list[dict] = field(default_factory=list)


# --- 抽象基类 ---

class BaseConnector(ABC):
    """连接器抽象基类，所有连接器必须实现此接口"""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def connect(self) -> None:
        """建立连接/认证"""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        ...

    @abstractmethod
    def health_check(self) -> HealthStatus:
        """健康检查"""
        ...

    @abstractmethod
    def list_entities(self) -> list[EntityInfo]:
        """列出支持的数据实体"""
        ...

    @abstractmethod
    def pull(
        self,
        entity: str,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        """从外部系统拉取数据"""
        ...

    @abstractmethod
    def push(self, entity: str, records: list[dict]) -> PushResult:
        """推送数据到外部系统"""
        ...

    @abstractmethod
    def get_schema(self, entity: str) -> dict:
        """获取实体字段结构"""
        ...


# --- 注册表 ---

class ConnectorRegistry:
    """连接器注册表，支持按类型查找"""

    def __init__(self):
        self._registry: dict[str, type[BaseConnector]] = {}

    def register(self, connector_type: str):
        """装饰器：注册连接器类"""
        def decorator(cls: type[BaseConnector]):
            self._registry[connector_type] = cls
            return cls
        return decorator

    def get(self, connector_type: str) -> type[BaseConnector]:
        """按类型查找连接器类"""
        if connector_type not in self._registry:
            raise ConnectorNotFoundError(
                f"连接器类型 '{connector_type}' 未注册。"
                f"已注册: {list(self._registry.keys())}"
            )
        return self._registry[connector_type]

    def list_types(self) -> list[str]:
        """列出所有已注册的连接器类型"""
        return list(self._registry.keys())


# 全局注册表实例
connector_registry = ConnectorRegistry()
register_connector = connector_registry.register
```

```python
# src/connectors/__init__.py
from src.connectors.base import (  # noqa: F401
    BaseConnector,
    ConnectorRegistry,
    connector_registry,
    register_connector,
    HealthStatus,
    EntityInfo,
    PushResult,
    ConnectorError,
    ConnectorNotFoundError,
    ConnectorPullError,
    ConnectorPushError,
)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd data_platform && python -m pytest tests/test_connector_base.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 添加 BaseConnector 抽象基类和 ConnectorRegistry 注册表

定义统一连接器接口（connect/disconnect/health_check/pull/push/get_schema），
实现装饰器注册模式和异常类。"
```

---

## Task 7: 凭据加密工具

**Files:**
- Create: `src/core/security.py`
- Test: `tests/test_config.py`（追加加密测试）

- [ ] **Step 1: 编写加密工具测试**

```python
# tests/test_config.py — 追加以下测试

from src.core.security import encrypt_value, decrypt_value


def test_encrypt_decrypt_roundtrip():
    """加密后解密应还原原始值"""
    key = "test-secret-key-for-encryption!!"  # 32 bytes
    original = "my_secret_password_123"
    encrypted = encrypt_value(original, key)
    assert encrypted != original
    decrypted = decrypt_value(encrypted, key)
    assert decrypted == original


def test_encrypt_produces_different_output():
    """同一明文多次加密应产生不同密文（因 IV 不同）"""
    key = "test-secret-key-for-encryption!!"
    val = "same_value"
    e1 = encrypt_value(val, key)
    e2 = encrypt_value(val, key)
    assert e1 != e2  # Fernet 使用随机 IV
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_config.py::test_encrypt_decrypt_roundtrip -v`
Expected: FAIL

- [ ] **Step 3: 实现加密工具**

```python
# src/core/security.py
import base64
import hashlib

from cryptography.fernet import Fernet


def _derive_key(secret: str) -> bytes:
    """从任意长度密钥派生 Fernet 兼容的 32 字节 base64 密钥"""
    key_bytes = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def encrypt_value(plaintext: str, secret_key: str) -> str:
    """加密字符串，返回 base64 编码的密文"""
    f = Fernet(_derive_key(secret_key))
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, secret_key: str) -> str:
    """解密密文，返回原始字符串"""
    f = Fernet(_derive_key(secret_key))
    return f.decrypt(ciphertext.encode()).decode()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd data_platform && python -m pytest tests/test_config.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 添加凭据加密工具（Fernet 对称加密）

用于加密存储连接器认证凭据，支持 encrypt_value/decrypt_value。"
```

---

## Task 8: 金蝶ERP连接器

**Files:**
- Create: `src/connectors/kingdee_erp.py`
- Test: `tests/test_connector_kingdee.py`

- [ ] **Step 1: 编写金蝶ERP连接器测试**

```python
# tests/test_connector_kingdee.py
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from src.connectors.kingdee_erp import KingdeeERPConnector
from src.connectors.base import (
    HealthStatus, EntityInfo, PushResult,
    ConnectorPullError, connector_registry,
)


@pytest.fixture
def kingdee_config():
    return {
        "base_url": "https://api.kingdee.com",
        "app_id": "test_app_id",
        "app_secret": "test_app_secret",
        "acct_id": "test_acct_id",
    }


@pytest.fixture
def connector(kingdee_config):
    return KingdeeERPConnector(config=kingdee_config)


def test_kingdee_registered():
    """金蝶ERP连接器应已注册到全局注册表"""
    cls = connector_registry.get("kingdee_erp")
    assert cls is KingdeeERPConnector


def test_kingdee_list_entities(connector):
    """应返回支持的实体列表"""
    entities = connector.list_entities()
    assert len(entities) > 0
    names = [e.name for e in entities]
    assert "sales_order" in names
    assert "purchase_order" in names


def test_kingdee_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"Result": {"ResponseStatus": {"IsSuccess": True}}}
        result = connector.health_check()
        assert result.status == "healthy"
        assert result.latency_ms is not None


def test_kingdee_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"
        assert "Connection refused" in result.error


def test_kingdee_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    mock_response = [
        {"FBillNo": "SO-001", "FDate": "2026-01-01", "FAmount": 1000},
        {"FBillNo": "SO-002", "FDate": "2026-01-02", "FAmount": 2000},
    ]
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="sales_order")
        assert len(records) == 2
        assert records[0]["FBillNo"] == "SO-001"


def test_kingdee_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("API Error 500")
        with pytest.raises(ConnectorPullError):
            connector.pull(entity="sales_order")


def test_kingdee_connect_gets_token(connector):
    """connect() 应获取会话令牌"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {
            "KDToken": "mock-token-123",
            "IsSuccessByAPI": True,
        }
        connector.connect()
        assert connector._token == "mock-token-123"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_connector_kingdee.py -v`
Expected: FAIL

- [ ] **Step 3: 实现金蝶ERP连接器**

```python
# src/connectors/kingdee_erp.py
import time
import logging
from datetime import datetime

import httpx

from src.connectors.base import (
    BaseConnector,
    register_connector,
    HealthStatus,
    EntityInfo,
    PushResult,
    ConnectorPullError,
    ConnectorPushError,
)

logger = logging.getLogger(__name__)

# 金蝶云星空支持的实体及对应 API FormId
KINGDEE_ENTITIES = {
    "sales_order": {"form_id": "SAL_SaleOrder", "description": "销售订单"},
    "purchase_order": {"form_id": "PUR_PurchaseOrder", "description": "采购订单"},
    "inventory": {"form_id": "STK_Inventory", "description": "库存"},
    "material": {"form_id": "BD_MATERIAL", "description": "物料"},
    "bom": {"form_id": "ENG_BOM", "description": "BOM"},
    "voucher": {"form_id": "GL_VOUCHER", "description": "财务凭证"},
}

MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


@register_connector("kingdee_erp")
class KingdeeERPConnector(BaseConnector):
    """金蝶云星空 ERP 连接器"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._token: str | None = None
        self._client = httpx.Client(timeout=30.0)

    def connect(self) -> None:
        """通过金蝶 Open API 获取会话令牌"""
        url = f"{self.config['base_url']}/k3cloud/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc"
        payload = {
            "acctID": self.config["acct_id"],
            "username": self.config.get("username", ""),
            "password": self.config.get("password", ""),
            "lcid": self.config.get("lcid", 2052),
        }
        result = self._request("POST", url, json=payload)
        if isinstance(result, dict) and result.get("KDToken"):
            self._token = result["KDToken"]
        elif isinstance(result, dict) and result.get("IsSuccessByAPI"):
            self._token = result.get("KDToken", "")
        else:
            self._token = str(result) if result else ""

    def disconnect(self) -> None:
        self._token = None
        self._client.close()

    def health_check(self) -> HealthStatus:
        start = time.time()
        try:
            self._request("GET", f"{self.config['base_url']}/k3cloud/")
            latency = (time.time() - start) * 1000
            return HealthStatus(status="healthy", latency_ms=round(latency, 2))
        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthStatus(
                status="unhealthy", latency_ms=round(latency, 2), error=str(e)
            )

    def list_entities(self) -> list[EntityInfo]:
        return [
            EntityInfo(name=name, description=meta["description"])
            for name, meta in KINGDEE_ENTITIES.items()
        ]

    def pull(
        self,
        entity: str,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        if entity not in KINGDEE_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        form_id = KINGDEE_ENTITIES[entity]["form_id"]
        url = f"{self.config['base_url']}/k3cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"

        filter_string = ""
        if since:
            filter_string = f"FModifyDate >= '{since.strftime('%Y-%m-%d %H:%M:%S')}'"
        if filters:
            extra = " AND ".join(f"{k} = '{v}'" for k, v in filters.items())
            filter_string = f"{filter_string} AND {extra}" if filter_string else extra

        payload = {
            "FormId": form_id,
            "FieldKeys": "",
            "FilterString": filter_string,
            "OrderString": "",
            "TopRowCount": 0,
            "StartRow": 0,
            "Limit": 2000,
        }

        try:
            result = self._request("POST", url, json=payload)
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"金蝶ERP拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        if entity not in KINGDEE_ENTITIES:
            raise ConnectorPushError(f"不支持的实体类型: {entity}")

        form_id = KINGDEE_ENTITIES[entity]["form_id"]
        url = f"{self.config['base_url']}/k3cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Save.common.kdsvc"

        success_count = 0
        failure_count = 0
        failures = []

        for record in records:
            try:
                payload = {"FormId": form_id, "Model": record}
                self._request("POST", url, json=payload)
                success_count += 1
            except Exception as e:
                failure_count += 1
                failures.append({
                    "record": record.get("FBillNo", "unknown"),
                    "error": str(e),
                })

        return PushResult(
            success_count=success_count,
            failure_count=failure_count,
            failures=failures,
        )

    def get_schema(self, entity: str) -> dict:
        """返回实体的字段结构（简化实现）"""
        return KINGDEE_ENTITIES.get(entity, {})

    def _request(self, method: str, url: str, **kwargs) -> dict | list:
        """带重试的 HTTP 请求"""
        headers = kwargs.pop("headers", {})
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.request(method, url, headers=headers, **kwargs)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", RETRY_BACKOFF[attempt]))
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()
                return resp.json()

            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF[attempt])
                    continue
                raise

        raise last_error
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd data_platform && python -m pytest tests/test_connector_kingdee.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 实现金蝶云星空 ERP 连接器

支持认证、健康检查、数据拉取（全量/增量）、数据推送，
带指数退避重试和限流处理。注册到全局连接器注册表。"
```

---

## Task 9: 字段映射转换服务

**Files:**
- Create: `src/services/__init__.py`
- Create: `src/services/field_mapping_service.py`
- Test: `tests/test_field_mapping.py`

- [ ] **Step 1: 编写字段映射服务测试**

```python
# tests/test_field_mapping.py
import pytest
from src.services.field_mapping_service import FieldMappingService


@pytest.fixture
def mapping_service():
    return FieldMappingService()


def test_simple_field_mapping(mapping_service):
    """简单字段映射：字段重命名"""
    mappings = [
        {"source_field": "FBillNo", "target_field": "order_number", "transform": None},
        {"source_field": "FDate", "target_field": "order_date", "transform": None},
        {"source_field": "FAmount", "target_field": "total_amount", "transform": None},
    ]
    source = {"FBillNo": "SO-001", "FDate": "2026-01-15", "FAmount": 1000.50}
    result = mapping_service.apply_mappings(source, mappings)
    assert result == {
        "order_number": "SO-001",
        "order_date": "2026-01-15",
        "total_amount": 1000.50,
    }


def test_date_format_transform(mapping_service):
    """日期格式转换"""
    mappings = [
        {
            "source_field": "FDate",
            "target_field": "order_date",
            "transform": "date_format",
            "transform_config": {"input": "%Y-%m-%dT%H:%M:%S", "output": "%Y-%m-%d"},
        },
    ]
    source = {"FDate": "2026-01-15T10:30:00"}
    result = mapping_service.apply_mappings(source, mappings)
    assert result["order_date"] == "2026-01-15"


def test_value_map_transform(mapping_service):
    """值映射转换"""
    mappings = [
        {
            "source_field": "FStatus",
            "target_field": "status",
            "transform": "value_map",
            "transform_config": {"map": {"A": "approved", "B": "pending", "C": "rejected"}},
        },
    ]
    source = {"FStatus": "A"}
    result = mapping_service.apply_mappings(source, mappings)
    assert result["status"] == "approved"


def test_concat_transform(mapping_service):
    """拼接转换"""
    mappings = [
        {
            "source_field": "FFirstName",
            "target_field": "name",
            "transform": "concat",
            "transform_config": {"fields": ["FFirstName", "FLastName"], "separator": " "},
        },
    ]
    source = {"FFirstName": "张", "FLastName": "三"}
    result = mapping_service.apply_mappings(source, mappings)
    assert result["name"] == "张 三"


def test_missing_source_field(mapping_service):
    """源字段不存在时应设为 None"""
    mappings = [
        {"source_field": "FMissing", "target_field": "value", "transform": None},
    ]
    source = {"FOther": "data"}
    result = mapping_service.apply_mappings(source, mappings)
    assert result["value"] is None


def test_reverse_mapping(mapping_service):
    """反向映射：统一字段 → 外部系统字段"""
    mappings = [
        {"source_field": "FBillNo", "target_field": "order_number", "transform": None},
        {"source_field": "FAmount", "target_field": "total_amount", "transform": None},
    ]
    unified = {"order_number": "SO-001", "total_amount": 2000}
    result = mapping_service.reverse_mappings(unified, mappings)
    assert result == {"FBillNo": "SO-001", "FAmount": 2000}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_field_mapping.py -v`
Expected: FAIL

- [ ] **Step 3: 实现字段映射服务**

```python
# src/services/__init__.py
（空文件）

# src/services/field_mapping_service.py
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FieldMappingService:
    """字段映射转换服务：在外部系统字段和统一模型字段之间进行转换"""

    def apply_mappings(self, source: dict, mappings: list[dict]) -> dict:
        """正向映射：外部系统字段 → 统一模型字段"""
        result = {}
        for m in mappings:
            source_field = m["source_field"]
            target_field = m["target_field"]
            transform = m.get("transform")
            transform_config = m.get("transform_config", {})

            raw_value = source.get(source_field)

            if transform and raw_value is not None:
                raw_value = self._apply_transform(
                    raw_value, transform, transform_config, source
                )

            result[target_field] = raw_value

        return result

    def reverse_mappings(self, unified: dict, mappings: list[dict]) -> dict:
        """反向映射：统一模型字段 → 外部系统字段"""
        result = {}
        for m in mappings:
            source_field = m["source_field"]  # 外部系统字段名
            target_field = m["target_field"]  # 统一模型字段名
            value = unified.get(target_field)
            if value is not None:
                result[source_field] = value
        return result

    def _apply_transform(
        self, value, transform: str, config: dict, source: dict
    ):
        """应用转换规则"""
        if transform == "date_format":
            return self._transform_date_format(value, config)
        elif transform == "value_map":
            return self._transform_value_map(value, config)
        elif transform == "concat":
            return self._transform_concat(value, config, source)
        elif transform == "split":
            return self._transform_split(value, config)
        else:
            logger.warning(f"未知的转换类型: {transform}")
            return value

    @staticmethod
    def _transform_date_format(value: str, config: dict) -> str:
        input_fmt = config.get("input", "%Y-%m-%d")
        output_fmt = config.get("output", "%Y-%m-%d")
        dt = datetime.strptime(value, input_fmt)
        return dt.strftime(output_fmt)

    @staticmethod
    def _transform_value_map(value, config: dict):
        mapping = config.get("map", {})
        return mapping.get(str(value), value)

    @staticmethod
    def _transform_concat(value, config: dict, source: dict) -> str:
        fields = config.get("fields", [])
        separator = config.get("separator", "")
        parts = [str(source.get(f, "")) for f in fields]
        return separator.join(parts)

    @staticmethod
    def _transform_split(value: str, config: dict):
        separator = config.get("separator", ",")
        index = config.get("index", 0)
        parts = value.split(separator)
        return parts[index] if index < len(parts) else value
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd data_platform && python -m pytest tests/test_field_mapping.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 实现字段映射转换服务

支持正向/反向映射，以及 date_format、value_map、concat、split 四种转换。"
```

---

## Task 10: 同步执行服务（拉取流程三阶段）

**Files:**
- Create: `src/services/sync_service.py`
- Test: `tests/test_sync_service.py`

- [ ] **Step 1: 编写同步服务测试**

```python
# tests/test_sync_service.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.services.sync_service import SyncExecutor

# 注意：此文件使用 conftest.py 中的 db_session fixture（SQLite 内存数据库）


@pytest.fixture
def mock_connector():
    conn = MagicMock()
    conn.pull.return_value = [
        {"FBillNo": "SO-001", "FDate": "2026-01-15", "FAmount": 1000},
        {"FBillNo": "SO-002", "FDate": "2026-01-16", "FAmount": 2000},
    ]
    return conn


@pytest.fixture
def mock_mappings():
    return [
        {"source_field": "FBillNo", "target_field": "order_number", "transform": None},
        {"source_field": "FDate", "target_field": "order_date", "transform": None},
        {"source_field": "FAmount", "target_field": "total_amount", "transform": None},
    ]


@pytest.fixture
def executor():
    return SyncExecutor()


def test_pull_phase(executor, mock_connector):
    """阶段1：拉取应调用 connector.pull 并返回原始数据"""
    records = executor.pull_phase(
        connector=mock_connector,
        entity="sales_order",
        since=None,
    )
    mock_connector.pull.assert_called_once_with(
        entity="sales_order", since=None, filters=None
    )
    assert len(records) == 2


def test_transform_phase(executor, mock_mappings):
    """阶段2：转换应将原始数据映射为统一格式"""
    raw_records = [
        {"FBillNo": "SO-001", "FDate": "2026-01-15", "FAmount": 1000},
    ]
    transformed, errors = executor.transform_phase(raw_records, mock_mappings)
    assert len(transformed) == 1
    assert len(errors) == 0
    assert transformed[0]["order_number"] == "SO-001"
    assert transformed[0]["total_amount"] == 1000


def test_transform_phase_with_error(executor):
    """阶段2：转换失败的记录应收集到错误列表"""
    mappings = [
        {
            "source_field": "FDate",
            "target_field": "date",
            "transform": "date_format",
            "transform_config": {"input": "%Y-%m-%d", "output": "%Y-%m-%d"},
        },
    ]
    records = [
        {"FDate": "2026-01-15"},  # 正确
        {"FDate": "invalid-date"},  # 会失败
    ]
    transformed, errors = executor.transform_phase(records, mappings)
    assert len(transformed) == 1
    assert len(errors) == 1
    assert "invalid-date" in str(errors[0])


def test_full_pull_sync(executor, mock_connector, mock_mappings, db_session):
    """完整拉取同步流程应存储数据并创建 SyncLog"""
    from src.models.connector import Connector
    from src.models.sync import SyncLog

    # 创建测试用连接器记录
    c = Connector(
        name="测试", connector_type="kingdee_erp", base_url="http://test",
        auth_config={}, enabled=True,
    )
    db_session.add(c)
    db_session.flush()

    result = executor.execute_pull(
        connector=mock_connector,
        connector_id=c.id,
        entity="sales_order",
        target_table="unified_orders",
        mappings=mock_mappings,
        session=db_session,
        since=None,
    )

    assert result["status"] in ("success", "partial_success")
    assert result["total_records"] == 2
    assert result["success_count"] + result["failure_count"] == 2

    # 验证 SyncLog 已创建
    logs = db_session.query(SyncLog).filter_by(connector_id=c.id).all()
    assert len(logs) == 1
    assert logs[0].status in ("success", "partial_success")
    assert logs[0].total_records == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_sync_service.py -v`
Expected: FAIL

- [ ] **Step 3: 实现同步执行服务**

```python
# src/services/sync_service.py
import logging
from datetime import datetime

from src.connectors.base import BaseConnector
from src.services.field_mapping_service import FieldMappingService

logger = logging.getLogger(__name__)


class SyncExecutor:
    """同步执行器：编排拉取/推送的三阶段流程"""

    def __init__(self):
        self._mapping_service = FieldMappingService()

    # --- 拉取流程 ---

    def pull_phase(
        self,
        connector: BaseConnector,
        entity: str,
        since: datetime | None = None,
    ) -> list[dict]:
        """阶段1：从外部系统拉取原始数据"""
        return connector.pull(entity=entity, since=since, filters=None)

    def transform_phase(
        self,
        raw_records: list[dict],
        mappings: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """阶段2：应用字段映射转换数据。返回 (成功列表, 错误列表)"""
        transformed = []
        errors = []

        for record in raw_records:
            try:
                mapped = self._mapping_service.apply_mappings(record, mappings)
                mapped["_raw"] = record  # 保留原始数据引用
                transformed.append(mapped)
            except Exception as e:
                errors.append({
                    "record": record,
                    "error": str(e),
                })

        return transformed, errors

    def store_phase(
        self,
        connector_id: int,
        entity: str,
        raw_records: list[dict],
        transformed_records: list[dict],
        target_table: str,
        session,
        sync_log_id: int | None = None,
    ) -> int:
        """阶段3：存储原始数据到 raw_data + 更新插入统一表。返回存储成功条数"""
        from datetime import timezone
        from src.models.raw_data import RawData

        stored = 0
        for i, raw in enumerate(raw_records):
            external_id = self._extract_external_id(raw, entity)
            if not external_id:
                continue

            # 更新插入 raw_data
            existing = session.query(RawData).filter_by(
                connector_id=connector_id,
                entity=entity,
                external_id=str(external_id),
            ).first()

            if existing:
                existing.data = raw
                existing.synced_at = datetime.now(timezone.utc)
                existing.sync_log_id = sync_log_id
            else:
                raw_data = RawData(
                    connector_id=connector_id,
                    entity=entity,
                    external_id=str(external_id),
                    data=raw,
                    sync_log_id=sync_log_id,
                )
                session.add(raw_data)

            stored += 1

        session.flush()

        # 更新插入统一表
        unified_model = self._get_unified_model(target_table)
        if unified_model is not None:
            for record in transformed_records:
                mapped = {k: v for k, v in record.items() if k != "_raw"}
                raw_ref = record.get("_raw", {})
                ext_id = self._extract_external_id(raw_ref, entity)
                if not ext_id:
                    continue

                existing_unified = session.query(unified_model).filter_by(
                    source_system=self._connector_type_for_id(connector_id, session),
                    external_id=str(ext_id),
                ).first()

                if existing_unified:
                    for k, v in mapped.items():
                        if hasattr(existing_unified, k):
                            setattr(existing_unified, k, v)
                else:
                    mapped["source_system"] = self._connector_type_for_id(
                        connector_id, session
                    )
                    mapped["external_id"] = str(ext_id)
                    # 只传统一模型实际拥有的列
                    valid_cols = {c.name for c in unified_model.__table__.columns}
                    filtered = {k: v for k, v in mapped.items() if k in valid_cols}
                    session.add(unified_model(**filtered))

            session.flush()

        return stored

    def execute_pull(
        self,
        connector: BaseConnector,
        connector_id: int,
        entity: str,
        target_table: str,
        mappings: list[dict],
        session,
        since: datetime | None = None,
    ) -> dict:
        """执行完整的拉取同步流程"""
        from datetime import timezone
        from src.models.sync import SyncLog

        # 阶段1：拉取
        raw_records = self.pull_phase(connector, entity, since)
        total = len(raw_records)

        if total == 0:
            # 即使无数据也记录日志
            log = SyncLog(
                sync_task_id=None,
                connector_id=connector_id,
                entity=entity,
                direction="pull",
                status="success",
                total_records=0,
                success_count=0,
                failure_count=0,
                finished_at=datetime.now(timezone.utc),
            )
            session.add(log)
            session.flush()
            return {
                "status": "success",
                "total_records": 0,
                "success_count": 0,
                "failure_count": 0,
                "errors": [],
            }

        # 阶段2：转换
        transformed, errors = self.transform_phase(raw_records, mappings)

        # 创建 sync_log 记录
        log = SyncLog(
            sync_task_id=None,
            connector_id=connector_id,
            entity=entity,
            direction="pull",
            status="running",
            total_records=total,
            success_count=0,
            failure_count=0,
        )
        session.add(log)
        session.flush()

        # 阶段3：存储（raw_data + 统一表）
        try:
            stored = self.store_phase(
                connector_id, entity, raw_records, transformed,
                target_table, session, sync_log_id=log.id,
            )
        except Exception as e:
            logger.error(f"存储阶段失败: {e}")
            log.status = "failure"
            log.failure_count = total
            log.error_details = {"phase": "store", "error": str(e)}
            log.finished_at = datetime.now(timezone.utc)
            session.flush()
            return {
                "status": "failure",
                "total_records": total,
                "success_count": 0,
                "failure_count": total,
                "errors": [{"phase": "store", "error": str(e)}],
            }

        success_count = len(transformed)
        failure_count = len(errors)
        status = "success" if failure_count == 0 else "partial_success"

        # 更新 sync_log
        log.status = status
        log.success_count = success_count
        log.failure_count = failure_count
        log.error_details = {"errors": errors} if errors else None
        log.finished_at = datetime.now(timezone.utc)
        session.flush()

        return {
            "status": status,
            "total_records": total,
            "success_count": success_count,
            "failure_count": failure_count,
            "errors": errors,
        }

    @staticmethod
    def _extract_external_id(record: dict, entity: str) -> str | None:
        """尝试从原始记录中提取外部 ID"""
        # 金蝶系统常见 ID 字段
        for key in ["FBillNo", "FNumber", "FID", "id", "Id", "ID"]:
            if key in record:
                return str(record[key])
        return None

    @staticmethod
    def _get_unified_model(target_table: str):
        """根据表名获取统一模型类"""
        from src.models.unified import (
            UnifiedCustomer, UnifiedOrder, UnifiedProduct,
            UnifiedInventory, UnifiedProject, UnifiedContact,
        )
        table_map = {
            "unified_customers": UnifiedCustomer,
            "unified_orders": UnifiedOrder,
            "unified_products": UnifiedProduct,
            "unified_inventory": UnifiedInventory,
            "unified_projects": UnifiedProject,
            "unified_contacts": UnifiedContact,
        }
        return table_map.get(target_table)

    @staticmethod
    def _connector_type_for_id(connector_id: int, session) -> str:
        """根据 connector_id 查询 connector_type"""
        from src.models.connector import Connector
        c = session.query(Connector).filter_by(id=connector_id).first()
        return c.connector_type if c else "unknown"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd data_platform && python -m pytest tests/test_sync_service.py -v`
Expected: 4 passed（含 SyncLog 创建验证）

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 实现同步执行服务（拉取流程三阶段）

包含 pull_phase（拉取）、transform_phase（转换）、store_phase（存储），
写入 raw_data + 统一表 + SyncLog，支持增量拉取和部分失败处理。"
```

---

## Task 11: 健康检查 API + Alembic 初始化

**Files:**
- Create: `src/api/__init__.py`
- Create: `src/api/health.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Modify: `src/main.py`
- Test: `tests/test_api_health.py`

- [ ] **Step 1: 编写健康检查 API 测试**

```python
# tests/test_api_health.py
from fastapi.testclient import TestClient
from src.main import app


client = TestClient(app)


def test_root():
    """根路径应返回应用信息"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "数据中台"


def test_health_endpoint():
    """健康检查端点应返回状态"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in ("healthy", "degraded", "unhealthy")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_api_health.py -v`
Expected: FAIL

- [ ] **Step 3: 实现健康检查 API**

```python
# src/api/__init__.py
（空文件）

# src/api/health.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    """平台健康检查"""
    # 简化版：后续 Task 会添加 DB/Redis/Celery 检查
    return {
        "status": "healthy",
        "components": {
            "database": "not_configured",
            "redis": "not_configured",
            "celery": "not_configured",
        },
    }
```

更新 `src/main.py`:

```python
from fastapi import FastAPI
from src.api.health import router as health_router

app = FastAPI(title="数据中台", version="0.1.0")

app.include_router(health_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"name": "数据中台", "version": "0.1.0"}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd data_platform && python -m pytest tests/test_api_health.py -v`
Expected: 2 passed

- [ ] **Step 5: 初始化 Alembic**

Run: `cd data_platform && alembic init alembic`
（如果目录已存在则跳过）

更新 `alembic/env.py` 关键部分，使其导入所有模型：

```python
# alembic/env.py 中添加（在 target_metadata 设置之前）
import src.models  # noqa: F401
from src.models.base import Base
target_metadata = Base.metadata
```

更新 `alembic.ini` 中的 `sqlalchemy.url`:

```ini
sqlalchemy.url = postgresql://dp_user:dp_pass@localhost/data_platform
```

- [ ] **Step 6: 运行全部测试确认通过**

Run: `cd data_platform && python -m pytest -v`
Expected: 全部通过（约 22 个测试）

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "feat: 添加健康检查 API 和 Alembic 数据库迁移初始化

GET /api/v1/health 返回平台健康状态，
Alembic 配置好模型元数据用于生成迁移脚本。"
```

---

## 完成检查

执行完所有 Task 后，项目应具备：

1. **项目脚手架**: pyproject.toml、docker-compose.yml、FastAPI 入口
2. **配置管理**: Pydantic Settings，支持环境变量
3. **数据库**: SQLAlchemy 2.0 + Alembic 迁移
4. **全部数据模型**: connectors、sync_tasks、sync_logs、raw_data、6张统一表、field_mappings、entity_schemas
5. **连接器框架**: BaseConnector 抽象基类 + ConnectorRegistry
6. **金蝶ERP连接器**: 完整实现，带认证、拉取、推送、重试
7. **字段映射服务**: 4种转换（date_format、value_map、concat、split）
8. **同步执行服务**: 拉取三阶段（pull → transform → store）
9. **健康检查 API**: GET /api/v1/health
10. **测试覆盖**: 约 22 个测试，全部通过

验证命令:

```bash
cd data_platform && python -m pytest -v --tb=short
```
