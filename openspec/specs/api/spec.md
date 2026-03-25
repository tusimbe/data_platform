# API 接口规范

## 目的

定义数据中台的 REST API 行为，提供统一数据查询、数据回写、连接器管理和同步任务管理等端点。

## 需求

### 需求：API 认证
系统应（SHALL）对所有 API 端点要求认证。

#### 场景：有效的 API 密钥
- 假设（GIVEN）请求在 Authorization 头中携带有效的 API 密钥
- 当（WHEN）调用任何 API 端点时
- 则（THEN）请求正常处理

#### 场景：缺少或无效的 API 密钥
- 假设（GIVEN）请求未携带 API 密钥或密钥无效
- 当（WHEN）调用任何 API 端点时
- 则（THEN）返回 401 Unauthorized 响应
- 且（AND）响应体包含错误信息

### 需求：统一数据查询
系统应（SHALL）提供端点用于查询统一模型数据，支持过滤、分页和排序。

#### 场景：查询统一记录列表
- 假设（GIVEN）unified_customers 中有数据
- 当（WHEN）调用 GET /api/v1/data/customers 时
- 则（THEN）返回分页的客户记录列表
- 且（AND）响应包含 total_count、page、page_size 和 items

#### 场景：过滤统一记录
- 假设（GIVEN）查询参数如 ?source_system=fenxiangxiaoke&status=active
- 当（WHEN）带过滤条件调用 GET /api/v1/data/customers 时
- 则（THEN）仅返回匹配的记录

#### 场景：查询单条记录
- 假设（GIVEN）一个记录 ID
- 当（WHEN）调用 GET /api/v1/data/customers/{id} 时
- 则（THEN）返回完整记录，包含数据溯源字段

#### 场景：未知实体类型
- 假设（GIVEN）不支持的实体类型
- 当（WHEN）调用 GET /api/v1/data/unknown_entity 时
- 则（THEN）返回 404 Not Found 响应

### 需求：原始数据查询
系统应（SHALL）提供端点用于按连接器和实体查询原始数据。

#### 场景：查询原始记录列表
- 假设（GIVEN）kingdee_erp / sales_order 存在原始数据
- 当（WHEN）调用 GET /api/v1/raw/kingdee_erp/sales_order 时
- 则（THEN）返回分页的原始 JSONB 记录

### 需求：数据回写
系统应（SHALL）提供端点用于将数据从中台推送到外部系统。

#### 场景：推送记录到外部系统
- 假设（GIVEN）有效的记录载荷
- 当（WHEN）调用 POST /api/v1/push/fenxiangxiaoke/customer 时
- 则（THEN）连接器将记录推送到外部系统
- 且（AND）响应包含 success_count 和 failure_count

#### 场景：推送到不可用的系统
- 假设（GIVEN）目标系统宕机
- 当（WHEN）调用 POST /api/v1/push/{connector}/{entity} 时
- 则（THEN）返回 502 Bad Gateway 响应
- 且（AND）响应体包含错误详情

### 需求：连接器管理
系统应（SHALL）提供连接器配置的增删改查端点。

#### 场景：列出连接器
- 当（WHEN）调用 GET /api/v1/connectors 时
- 则（THEN）返回所有已配置的连接器，包含类型、名称、状态（启用/禁用）和最近健康检查结果
- 且（AND）响应中不包含认证凭据

#### 场景：创建连接器
- 假设（GIVEN）有效的连接器参数
- 当（WHEN）调用 POST /api/v1/connectors 时
- 则（THEN）创建连接器配置
- 且（AND）返回 201 Created 响应，包含新连接器的 ID

#### 场景：更新连接器
- 假设（GIVEN）已有的连接器 ID 和更新后的参数
- 当（WHEN）调用 PUT /api/v1/connectors/{id} 时
- 则（THEN）配置被更新
- 且（AND）返回 200 OK 响应

#### 场景：删除连接器
- 假设（GIVEN）已有的连接器 ID
- 当（WHEN）调用 DELETE /api/v1/connectors/{id} 时
- 则（THEN）连接器被软删除（禁用，不物理删除）
- 且（AND）关联的同步任务也被禁用

### 需求：同步任务管理
系统应（SHALL）提供端点用于管理同步任务和查看同步日志。

#### 场景：列出同步任务
- 当（WHEN）调用 GET /api/v1/sync-tasks 时
- 则（THEN）返回所有同步任务，包含状态、上次执行时间和下次调度时间

#### 场景：创建同步任务
- 假设（GIVEN）有效的参数（connector_id、entity、direction、cron）
- 当（WHEN）调用 POST /api/v1/sync-tasks 时
- 则（THEN）创建同步任务并注册调度

#### 场景：手动触发同步
- 假设（GIVEN）已有的同步任务 ID
- 当（WHEN）调用 POST /api/v1/sync-tasks/{id}/trigger 时
- 则（THEN）同步任务立即入队执行
- 且（AND）返回 202 Accepted 响应

#### 场景：查看同步日志
- 当（WHEN）调用 GET /api/v1/sync-logs 时
- 则（THEN）返回分页的同步执行日志
- 且（AND）支持按 connector_id、entity、status 和日期范围过滤

### 需求：健康检查端点
系统应（SHALL）提供健康检查端点。

#### 场景：平台健康
- 当（WHEN）调用 GET /api/v1/health 时
- 则（THEN）响应包含：
  - 数据库连通性状态
  - Redis 连通性状态
  - Celery Worker 状态
  - 整体状态（healthy/degraded/unhealthy）

### 需求：统一错误响应
系统应（SHALL）在所有端点返回一致的错误响应格式。

#### 场景：错误响应格式
- 假设（GIVEN）任何 API 错误发生
- 则（THEN）响应体包含：{"error": {"code": "...", "message": "...", "details": ...}}
- 且（AND）使用恰当的 HTTP 状态码（400、401、404、409、500、502）

### 需求：API 分页
所有列表端点应（SHALL）支持偏移量分页。

#### 场景：分页响应
- 假设（GIVEN）一个列表端点
- 当（WHEN）以 ?page=2&page_size=20 调用时
- 则（THEN）响应返回第 2 页的数据，每页 20 条
- 且（AND）包含完整结果集的 total_count
