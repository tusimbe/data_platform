# 企业数据中台 设计规范

## 概述

企业数据中台，用于收集、管理和分发各业务系统的数据。平台通过统一的连接器框架接入6个外部系统，采用双层存储模型（原始层 + 统一层），并提供 REST API 进行数据查询和回写。

## 背景

### 需要接入的业务系统

| 系统 | 类型 | 接口方式 | 核心数据实体 |
|------|------|----------|-------------|
| 金蝶云星空 | ERP | REST API (Open API) | 销售订单、采购订单、库存、BOM、财务凭证 |
| 金蝶PLM | PLM | REST API | 产品、物料、设计文档、变更单 |
| 纷享销客 | CRM | REST API (开放平台) | 客户、联系人、商机、合同、回款 |
| 飞书 | OA | REST API (开放平台) | 审批流、组织架构、日程、文档 |
| 禅道 | 项目管理 | REST API | 项目、需求、任务、Bug、迭代 |
| 领星ERP | 跨境电商ERP | REST API (开放平台) | 商品、订单、库存、物流、结算 |

### 技术栈

- **语言：** Python 3.11+
- **框架：** FastAPI
- **数据库：** PostgreSQL（支持 JSONB）
- **任务队列：** Celery + Redis
- **ORM：** SQLAlchemy 2.0 + Alembic（数据库迁移）
- **部署：** 国内公有云，Docker 容器化

### 数据规模

- 小规模：每天约 1 万条记录
- 定时同步（基于 cron），非实时流式处理
- 双向：从各系统采集数据 + 回写数据到各系统

## 架构设计

### 四层架构

```
┌──────────────────────────────────────────────────────┐
│  第四层：管理后台 (Web)                                │
│  连接器配置 / 同步任务管理 / 数据查询 / 监控            │
├──────────────────────────────────────────────────────┤
│  第三层：数据服务层 (FastAPI)                           │
│  REST API / 统一查询接口 / 数据回写 / 认证鉴权          │
├──────────────────────────────────────────────────────┤
│  第二层：核心引擎                                      │
│  连接器注册中心 / 模型注册中心 / 任务调度器              │
├──────────────────────────────────────────────────────┤
│  第一层：连接器层                                      │
│  金蝶ERP / 金蝶PLM / 纷享销客 / 飞书 / 禅道 / 领星ERP  │
├──────────────────────────────────────────────────────┤
│  存储层：PostgreSQL                                    │
│  统一数据模型 / 原始数据 / 元数据 / 同步日志             │
└──────────────────────────────────────────────────────┘
```

### 项目目录结构

```
data_platform/
├── openspec/                    # OpenSpec 规范目录
│   ├── specs/                   # 行为规范（事实来源）
│   │   ├── connectors/          # 连接器规范
│   │   ├── data-model/          # 数据模型规范
│   │   ├── sync-engine/         # 同步引擎规范
│   │   └── api/                 # API 接口规范
│   ├── changes/                 # 当前变更
│   └── config.yaml
├── src/
│   ├── connectors/              # 连接器实现
│   │   ├── base.py              # 抽象基类
│   │   ├── kingdee_erp.py       # 金蝶ERP
│   │   ├── kingdee_plm.py       # 金蝶PLM
│   │   ├── fenxiangxiaoke.py    # 纷享销客
│   │   ├── feishu.py            # 飞书
│   │   ├── zentao.py            # 禅道
│   │   └── lingxing.py          # 领星ERP
│   ├── models/                  # SQLAlchemy 数据模型
│   ├── services/                # 业务逻辑层
│   ├── api/                     # FastAPI 路由
│   ├── tasks/                   # Celery 异步任务
│   ├── core/                    # 配置、认证、通用工具
│   └── main.py                  # 应用入口
├── tests/                       # 测试
├── alembic/                     # 数据库迁移
├── pyproject.toml
└── docker-compose.yml           # 本地开发环境 (PG + Redis)
```

## 组件设计

### 1. 连接器框架

#### 抽象基类

所有连接器实现统一接口：

```python
class BaseConnector(ABC):
    # 生命周期
    connect() -> None             # 建立连接/认证
    disconnect() -> None          # 断开连接
    health_check() -> HealthStatus  # 健康检查

    # 数据读取（外部系统 → 中台）
    list_entities() -> list[EntityInfo]  # 列出支持的数据实体
    pull(entity: str, since: datetime | None, filters: dict) -> list[dict]  # 拉取数据

    # 数据写入（中台 → 外部系统）
    push(entity: str, records: list[dict]) -> PushResult  # 推送数据

    # 元数据
    get_schema(entity: str) -> EntitySchema  # 获取实体字段结构
```

#### 连接器注册中心

- 连接器通过注册模式自注册
- 配置信息存储在 `connectors` 表（类型、认证凭据、启用状态）
- 认证凭据静态加密存储

### 2. 数据模型 — 双层存储

#### 第一层：原始数据

```sql
raw_data (
    id              BIGSERIAL PRIMARY KEY,
    connector_id    INTEGER REFERENCES connectors(id),
    entity          VARCHAR(100),      -- 如："sales_order"
    external_id     VARCHAR(255),      -- 来源系统中的 ID
    data            JSONB,             -- 原始数据原样保存
    synced_at       TIMESTAMPTZ,       -- 同步时间
    sync_log_id     BIGINT REFERENCES sync_logs(id),
    UNIQUE(connector_id, entity, external_id)
)
```

以 JSONB 格式存储各系统的原始数据，不做格式限制，便于追溯和重新处理。

#### 第二层：统一模型

按业务领域设计标准化表：

- `unified_customers` — 统一客户表（来源：CRM、ERP）
- `unified_orders` — 统一订单表（来源：ERP、领星）
- `unified_products` — 统一产品/物料表（来源：ERP、PLM、领星）
- `unified_inventory` — 统一库存表（来源：ERP、领星）
- `unified_projects` — 统一项目表（来源：禅道）
- `unified_contacts` — 统一联系人表（来源：CRM、飞书）

每张统一表包含：
- `source_system` — 数据来源系统
- `external_id` — 来源系统中的 ID
- `source_data_id` — 关联 raw_data 表，实现数据溯源
- `created_at`、`updated_at` — 时间戳
- 对应业务领域的标准字段

#### 平台元数据表

| 表名 | 用途 |
|------|------|
| `connectors` | 连接器配置（类型、认证信息、启用状态） |
| `sync_tasks` | 同步任务定义（连接器、实体、cron 表达式、方向） |
| `sync_logs` | 同步执行日志（开始/结束时间、状态、条数、错误） |
| `entity_schemas` | 各系统实体的字段结构元数据 |
| `field_mappings` | 外部系统字段 ↔ 统一模型字段的映射规则 |

### 3. 同步引擎

#### 拉取流程（入站）

```
Celery Beat（定时触发）
    │
    ▼
阶段1：拉取 — connector.pull() 从外部系统获取记录
    │
    ▼
阶段2：转换 — 应用字段映射，数据清洗，格式标准化
    │
    ▼
阶段3：存储 — 更新 raw_data + 更新统一表 + 写入同步日志
```

#### 推送流程（出站）

```
API 调用或定时触发
    │
    ▼
阶段1：读取 — 从数据库查询待回写记录
    │
    ▼
阶段2：转换 — 反向字段映射，适配目标系统格式
    │
    ▼
阶段3：推送 — connector.push() 发送数据到外部系统 + 写入同步日志
```

#### 同步日志

每次同步执行记录：开始/结束时间、方向、实体、连接器、总条数、成功/失败条数、错误详情。

### 4. API 设计

```
# 统一数据查询
GET  /api/v1/data/{entity}              # 查询统一模型数据
GET  /api/v1/data/{entity}/{id}         # 查询单条记录
GET  /api/v1/raw/{connector}/{entity}   # 查询原始数据

# 数据回写
POST /api/v1/push/{connector}/{entity}  # 推送数据到指定系统

# 连接器管理
GET  /api/v1/connectors                 # 列出所有连接器
POST /api/v1/connectors                 # 新增连接器配置
PUT  /api/v1/connectors/{id}            # 更新配置

# 同步任务管理
GET  /api/v1/sync-tasks                 # 列出同步任务
POST /api/v1/sync-tasks/{id}/trigger    # 手动触发同步
GET  /api/v1/sync-logs                  # 查看同步日志

# 健康检查
GET  /api/v1/health                     # 平台健康检查
```

## 子项目拆分

实施分为 7 个子项目，每个子项目遵循独立的 OpenSpec 规范 → 计划 → 实现 周期：

| # | 子项目 | 内容 | 优先级 |
|---|--------|------|--------|
| 1 | 基础平台 | 项目脚手架、数据库、配置、认证鉴权 | P0 |
| 2 | 连接器框架 + 首个连接器 | 连接器抽象基类 + 金蝶ERP 连接器 | P0 |
| 3 | 数据模型与存储 | 统一数据模型、原始数据层、元数据表 | P0 |
| 4 | 其余连接器 | PLM、CRM、飞书、禅道、领星ERP 连接器 | P1 |
| 5 | 数据服务层 | 统一查询 API、数据回写 API | P1 |
| 6 | 调度与监控 | Celery Beat 调度、同步状态监控、日志告警 | P1 |
| 7 | 管理后台 | Web 管理界面、连接器配置界面、同步任务看板 | P2 |

## 成功标准

1. 所有 6 个连接器能成功从各自系统拉取数据
2. 数据同时存储在原始层（JSONB）和统一层（结构化表）
3. 字段映射可配置，无需修改代码
4. 至少金蝶ERP 和 CRM 支持数据回写
5. 同步任务按计划执行，有完善的日志记录和错误处理
6. REST API 提供跨所有集成数据的统一查询
7. OpenSpec 规范作为所有行为的事实来源持续维护

## 非目标（初版不做）

- 实时流处理 / CDC（变更数据捕获）
- 复杂数据分析 / BI 看板
- 机器学习或 AI 驱动的数据处理
- 多租户支持
- 自定义主题等高级 UI 定制
