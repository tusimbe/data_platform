# P1 子项目5：数据服务层 API 设计

## 概述

为数据中台的已有数据层加上完整的 REST API 外壳，提供统一数据查询、数据回写、连接器管理、同步任务管理和健康检查功能。

**前置条件**：P0（基础架构）和 P1 子项目4（6个连接器）已完成，100 个测试通过。

**约束**：
- 当前无 Redis/Celery（子项目6 的工作），同步任务触发采用同步执行
- 测试使用 pytest + TestClient + SQLite 内存数据库

---

## 架构：方案 A — 扁平路由 + 独立服务

每个 API 端点组一个路由文件，每组对应一个服务类。共享依赖集中在 `deps.py`。

### 文件结构

```
src/api/
  deps.py                  # 共享依赖: get_db, API Key 认证, 分页
  errors.py                # 统一错误处理 exception_handlers
  schemas/
    __init__.py
    common.py              # ErrorResponse, PaginatedResponse, PaginationParams
    connector.py           # ConnectorCreate, ConnectorUpdate, ConnectorResponse
    sync.py                # SyncTaskCreate/Update/Response, SyncLogResponse
    data.py                # UnifiedDataResponse, RawDataResponse, PushRequest/Response
  routes/
    __init__.py
    health.py              # GET /health (增强版，替换现有 stub)
    connectors.py          # 连接器 CRUD
    sync_tasks.py          # 同步任务 CRUD + 手动触发
    sync_logs.py           # 同步日志查询
    data.py                # 统一数据 + 原始数据查询
    push.py                # 数据回写
src/services/
  connector_service.py     # 连接器 CRUD + 凭证加密 + 软删除级联
  sync_task_service.py     # 同步任务管理 + 验证 + 触发执行
  push_service.py          # 数据推送执行（连接器实例化 + 连接管理）
  # 已有: field_mapping_service.py, sync_service.py
```

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `src/main.py` | 注册所有路由、错误处理、启动事件 |
| `src/api/health.py` | 替换为增强版（移至 routes/health.py） |
| `src/api/__init__.py` | 更新导出 |
| `tests/test_api_health.py` | 更新为增强版测试 |

---

## Section 1：基础设施层

### 1.1 API Key 认证 (`deps.py`)

FastAPI `Depends` 依赖函数 `get_current_api_key()`：
- 从 `Authorization: Bearer <key>` 或 `X-API-Key: <key>` 请求头提取 key
- 与 `settings.API_KEY` 比对
- 不匹配返回 401 `{"error": {"code": "UNAUTHORIZED", "message": "Invalid or missing API key"}}`
- 健康检查端点 `GET /api/v1/health` 免认证

### 1.2 统一错误处理 (`errors.py`)

在 FastAPI app 上注册全局 exception handlers。所有错误响应格式：

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Connector with id 99 not found",
    "details": null
  }
}
```

处理的异常类型：
- `HTTPException` → 对应 HTTP 状态码 + 标准错误码（NOT_FOUND, BAD_REQUEST 等）
- `RequestValidationError` → 422 + `VALIDATION_ERROR` + details 包含字段错误
- 未捕获异常 → 500 + `INTERNAL_ERROR`（不暴露内部细节）

### 1.3 分页工具 (`deps.py`)

共享分页参数依赖 `PaginationParams`：
- `page`: int, 默认 1, 最小 1
- `page_size`: int, 默认 20, 最小 1, 最大 100

统一分页响应格式：

```json
{
  "items": [...],
  "total_count": 150,
  "page": 1,
  "page_size": 20
}
```

提供 `paginate(query, params) -> dict` 工具函数，接收 SQLAlchemy query 和分页参数，返回上述格式。

### 1.4 Pydantic Schemas (`schemas/`)

**`common.py`**:
- `ErrorDetail`: `code` (str), `message` (str), `details` (Any | None)
- `ErrorResponse`: `error` (ErrorDetail)
- `PaginatedResponse[T]`: 泛型分页响应

**`connector.py`**:
- `ConnectorCreate`: `name`, `connector_type`, `base_url`, `auth_config` (dict), `description` (optional)
- `ConnectorUpdate`: 所有字段 optional
- `ConnectorResponse`: `id`, `name`, `connector_type`, `base_url`, `has_auth_config` (bool), `enabled`, `description`, `created_at`, `updated_at`。**不包含 auth_config**。

**`sync.py`**:
- `SyncTaskCreate`: `connector_id`, `entity`, `direction`, `cron_expression` (optional), `enabled`
- `SyncTaskUpdate`: 所有字段 optional
- `SyncTaskResponse`: 全字段 + `last_sync_at`
- `SyncLogResponse`: 全字段

**`data.py`**:
- `PushRequest`: `records` (list[dict])
- `PushResponse`: `success_count`, `failure_count`, `failures` (list)

统一数据和原始数据的响应直接使用 `dict` 序列化（JSONB 内容动态）。

---

## Section 2：数据查询 API

### 路由文件：`routes/data.py`

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/data/{entity}` | GET | 分页查询统一数据表 |
| `/api/v1/data/{entity}/{id}` | GET | 按 ID 查单条记录 |
| `/api/v1/raw/{connector_type}/{entity}` | GET | 分页查询原始数据 |

### 实体路由映射

`ENTITY_REGISTRY` 字典管理 URL entity → SQLAlchemy model 映射：

| URL entity | Model |
|------------|-------|
| `customers` | `UnifiedCustomer` |
| `orders` | `UnifiedOrder` |
| `products` | `UnifiedProduct` |
| `inventory` | `UnifiedInventory` |
| `projects` | `UnifiedProject` |
| `contacts` | `UnifiedContact` |

无效实体返回 404 `ENTITY_NOT_FOUND`。

### 动态过滤

查询参数自动映射为 WHERE 条件。例如：

```
GET /api/v1/data/customers?status=active&source_system=fenxiangxiaoke
→ WHERE status='active' AND source_system='fenxiangxiaoke'
```

- 只允许模型上存在的列名
- 非法列名返回 400 `INVALID_FILTER`

### 排序

支持 `?sort_by=created_at&sort_order=desc`，默认按 `created_at` 降序。`sort_by` 必须是模型的有效列名。

### 原始数据查询

`GET /api/v1/raw/{connector_type}/{entity}`：
1. 通过 `connector_type` 查 `Connector` 表找到所有匹配的 `connector_id`
2. 按 `connector_id` + `entity` 过滤 `RawData` 表
3. 返回分页的 `data` (JSONB) 字段内容

---

## Section 3：数据回写 API

### 路由文件：`routes/push.py`

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/push/{connector_type}/{entity}` | POST | 向目标系统推送数据 |

### 请求体

```json
{
  "records": [
    {"name": "客户A", "phone": "138..."},
    {"name": "客户B", "phone": "139..."}
  ]
}
```

### 执行流程

1. 通过 `connector_type` 查 DB 找到 enabled 的连接器配置
2. 通过 `connector_registry.get(connector_type)` 实例化连接器
3. 调用 `connector.connect()` 建立连接
4. 调用 `connector.push(entity, records)` 推送
5. 返回 `PushResult`：`{"success_count": N, "failure_count": M, "failures": [...]}`
6. 调用 `connector.disconnect()` 清理（在 finally 中确保执行）

### 错误处理

- 连接器不存在或未启用 → 404 `CONNECTOR_NOT_FOUND`
- 连接器连接失败 → 502 Bad Gateway `CONNECTOR_UNAVAILABLE`
- 部分失败 → 200，在 response 的 `failures` 中列出失败记录

### 服务层：`push_service.py`

封装上述流程：
- `execute_push(connector_type, entity, records, session) -> PushResult`
- 负责连接器实例化、连接管理、异常封装

---

## Section 4：连接器管理 API

### 路由文件：`routes/connectors.py`

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/connectors` | GET | 分页列出所有连接器 |
| `/api/v1/connectors` | POST | 创建连接器 |
| `/api/v1/connectors/{id}` | GET | 获取单个连接器详情 |
| `/api/v1/connectors/{id}` | PUT | 更新连接器配置 |
| `/api/v1/connectors/{id}` | DELETE | 软删除（禁用）连接器 |

### 创建请求体

```json
{
  "name": "金蝶ERP-生产环境",
  "connector_type": "kingdee_erp",
  "base_url": "https://erp.company.com",
  "auth_config": {"acct_id": "xxx", "username": "admin", "password": "***"},
  "description": "生产环境金蝶ERP"
}
```

### 凭证安全

- `auth_config` 写入时使用 `security.encrypt_value()` 加密存储
- 响应中**不返回** `auth_config` 字段
- 仅返回 `has_auth_config: true/false` 标识是否已配置凭证

### 软删除行为（DELETE）

1. 设置 `connector.enabled = False`
2. 查找关联的所有 `SyncTask`，全部设置 `enabled = False`
3. 返回 204 No Content

### 验证

- `connector_type` 必须在 `connector_registry.list_types()` 中，否则 400 `INVALID_CONNECTOR_TYPE`
- `name` 不能重复，否则 409 `CONNECTOR_NAME_CONFLICT`

### 服务层：`connector_service.py`

- `list_connectors(session, params) -> PaginatedResponse`
- `get_connector(session, id) -> Connector`
- `create_connector(session, data) -> Connector`
- `update_connector(session, id, data) -> Connector`
- `delete_connector(session, id) -> None`（软删除 + 级联禁用）

---

## Section 5：同步任务管理 API

### 路由文件：`routes/sync_tasks.py` + `routes/sync_logs.py`

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/sync-tasks` | GET | 分页列出同步任务 |
| `/api/v1/sync-tasks` | POST | 创建同步任务 |
| `/api/v1/sync-tasks/{id}` | GET | 获取单个任务详情 |
| `/api/v1/sync-tasks/{id}` | PUT | 更新同步任务 |
| `/api/v1/sync-tasks/{id}` | DELETE | 删除同步任务 |
| `/api/v1/sync-tasks/{id}/trigger` | POST | 手动触发同步 |
| `/api/v1/sync-logs` | GET | 分页查询同步日志 |

### 创建请求体

```json
{
  "connector_id": 1,
  "entity": "customer",
  "direction": "pull",
  "cron_expression": "0 */2 * * *",
  "enabled": true
}
```

### 验证

- `connector_id` 必须存在且已启用，否则 400 `INVALID_CONNECTOR`
- `direction` 仅允许 `"pull"` 或 `"push"`
- `entity` 应在对应连接器的 `list_entities()` 中

### 手动触发（`POST /sync-tasks/{id}/trigger`）

当前无 Celery，采用同步执行：
- 直接调用 `SyncExecutor.execute_pull()` 或对应推送逻辑
- 返回 200 + 执行结果 `{"status": "success", "total_records": N, "success_count": N, ...}`
- 后续子项目6 接入 Celery 后改为 202 Accepted + 异步执行

### 同步日志查询

- 支持过滤：`?connector_id=1&entity=customer&status=success`
- 按 `started_at` 降序排列
- 分页返回

### 服务层：`sync_task_service.py`

- `list_sync_tasks(session, params, filters) -> PaginatedResponse`
- `get_sync_task(session, id) -> SyncTask`
- `create_sync_task(session, data) -> SyncTask`
- `update_sync_task(session, id, data) -> SyncTask`
- `delete_sync_task(session, id) -> None`
- `trigger_sync(session, id) -> dict`（同步执行，返回结果）
- `list_sync_logs(session, params, filters) -> PaginatedResponse`

---

## Section 6：健康检查增强 + main.py 改造

### 健康检查增强 (`routes/health.py`)

替换现有 stub 实现：

```json
{
  "status": "healthy",
  "components": {
    "database": {"status": "healthy", "latency_ms": 2.5},
    "redis": {"status": "not_configured"},
    "celery": {"status": "not_configured"}
  },
  "version": "0.1.0"
}
```

- **database**：执行 `SELECT 1` 验证连接，测量延迟
- **redis/celery**：当前返回 `"not_configured"`，子项目6接入后改为真实检查
- **overall status**：全部 healthy/not_configured → `"healthy"`，有 unhealthy → `"degraded"`，database unhealthy → `"unhealthy"`
- 此端点**免认证**

### main.py 改造

```python
app = FastAPI(title="数据中台", version="0.1.0")

# 注册统一错误处理
register_error_handlers(app)

# 注册所有路由
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(connectors_router, prefix="/api/v1", tags=["connectors"])
app.include_router(sync_tasks_router, prefix="/api/v1", tags=["sync"])
app.include_router(sync_logs_router, prefix="/api/v1", tags=["sync"])
app.include_router(data_router, prefix="/api/v1", tags=["data"])
app.include_router(push_router, prefix="/api/v1", tags=["push"])

# 启动事件：初始化数据库
@app.on_event("startup")
async def startup():
    init_db(settings.DATABASE_URL)
```

---

## 测试策略

使用 pytest + FastAPI TestClient + SQLite 内存数据库。每个路由文件对应一个测试文件。

| 测试文件 | 覆盖内容 | 预估测试数 |
|----------|----------|-----------|
| `test_api_deps.py` | API Key 认证、分页参数 | ~5 |
| `test_api_errors.py` | 统一错误格式 | ~4 |
| `test_api_connectors.py` | CRUD + 软删除 + 凭证隐藏 | ~10 |
| `test_api_sync_tasks.py` | CRUD + 手动触发 | ~10 |
| `test_api_sync_logs.py` | 查询 + 过滤 | ~5 |
| `test_api_data.py` | 统一/原始数据查询 + 过滤 + 排序 | ~10 |
| `test_api_push.py` | 推送 + 错误处理 | ~6 |
| `test_api_health.py` | 增强健康检查（替换现有） | ~4 |
| **总计** | | **~54 tests** |

测试中 mock 外部连接器调用，使用真实的 SQLAlchemy session（SQLite 内存数据库）。
