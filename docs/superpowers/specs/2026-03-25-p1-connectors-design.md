# P1 子项目4：剩余连接器设计

## 概述

本文档定义企业数据中台 P1 阶段子项目4的设计：实现剩余5个外部系统连接器（金蝶PLM、纷享销客CRM、飞书、禅道、领星ERP），使平台能够从这些系统拉取数据并推送数据回写。

## 目标

- 实现5个连接器，每个遵循 `BaseConnector` 抽象接口
- 为每个连接器配置字段映射，将数据写入统一表
- 提供完整的单元测试覆盖
- 禅道连接器因无 API 文档，先用 mock 实现，预留真实调用结构

## 连接器清单

| # | 连接器 | 文件 | 认证方式 | 文档状态 |
|---|--------|------|----------|----------|
| 1 | 金蝶PLM | `kingdee_plm.py` | Session Token | 有文档 |
| 2 | 纷享销客CRM | `fenxiangxiaoke.py` | OAuth2 Client Credentials | 有文档 |
| 3 | 飞书 | `feishu.py` | OAuth2 (tenant_access_token) | 有文档 |
| 4 | 禅道 | `zentao.py` | Session Token | 无文档，mock |
| 5 | 领星ERP | `lingxing.py` | HMAC 签名 | 有文档 |

## 架构设计

### 文件结构

```
src/connectors/
├── __init__.py              # 导出所有连接器
├── base.py                  # 已有：BaseConnector + ConnectorRegistry
├── kingdee_erp.py           # 已有：金蝶ERP连接器
├── kingdee_plm.py           # 新增
├── fenxiangxiaoke.py        # 新增
├── feishu.py                # 新增
├── zentao.py                # 新增
└── lingxing.py              # 新增

tests/
├── test_connector_kingdee_plm.py
├── test_connector_fenxiangxiaoke.py
├── test_connector_feishu.py
├── test_connector_zentao.py
└── test_connector_lingxing.py
```

### 连接器接口（复用 BaseConnector）

每个连接器必须实现：

```python
class XxxConnector(BaseConnector):
    def connect(self) -> None: ...           # 认证获取 token
    def disconnect(self) -> None: ...        # 清理连接
    def health_check(self) -> HealthStatus: ...
    def list_entities(self) -> list[EntityInfo]: ...
    def pull(self, entity, since=None, filters=None) -> list[dict]: ...
    def push(self, entity, records) -> PushResult: ...
    def get_schema(self, entity) -> dict: ...
```

### 公共能力（复用 P0）

- **重试机制**：指数退避（1s, 2s, 4s），最多3次，处理超时和 5xx 错误
- **限流处理**：识别 429 响应，读取 Retry-After 头等待后重试
- **凭据加密**：敏感配置使用 `src/core/security.py` 加解密
- **字段映射**：使用 `FieldMappingService` 进行数据转换

---

## 连接器详细设计

### 1. 金蝶PLM连接器

**注册名**：`kingdee_plm`

**认证方式**：Session Token（与金蝶ERP相同）
- `connect()` 调用 ValidateUser 接口获取 KDToken
- Token 存储在实例变量，请求时通过 Header 传递

**支持实体**：

| 实体名 | FormId | 描述 | 目标统一表 |
|--------|--------|------|-----------|
| `product` | PLM_Product | 产品主数据 | unified_products |
| `material` | PLM_Material | 物料主数据 | unified_products |
| `bom` | PLM_BOM | 物料清单 | unified_products |
| `change_order` | PLM_ECO | 工程变更单 | unified_projects |

**配置结构**：
```python
{
    "base_url": "https://plm.kingdee.com",
    "acct_id": "账套ID",
    "username": "用户名",
    "password": "密码（加密存储）",
    "lcid": 2052  # 语言
}
```

---

### 2. 纷享销客CRM连接器

**注册名**：`fenxiangxiaoke`

**认证方式**：OAuth2 Client Credentials
- 调用 `/cgi/corpAccessToken/get` 获取 access_token
- Token 有效期约2小时，需实现过期刷新逻辑
- `_ensure_token()` 内部方法检查并刷新

**支持实体**：

| 实体名 | API 路径 | 描述 | 目标统一表 |
|--------|----------|------|-----------|
| `customer` | /cgi/crm/custom/v2/list | 客户 | unified_customers |
| `contact` | /cgi/crm/contact/list | 联系人 | unified_contacts |
| `opportunity` | /cgi/crm/opportunity/list | 商机 | unified_orders |
| `contract` | /cgi/crm/contract/list | 合同 | unified_orders |

**配置结构**：
```python
{
    "base_url": "https://open.fxiaoke.com",
    "app_id": "应用ID",
    "app_secret": "应用密钥（加密存储）",
    "permanent_code": "企业永久授权码"
}
```

---

### 3. 飞书连接器

**注册名**：`feishu`

**认证方式**：OAuth2 (tenant_access_token)
- 调用 `/open-apis/auth/v3/tenant_access_token/internal` 获取 token
- Token 有效期2小时，需实现过期刷新
- 使用 app_id + app_secret 请求

**支持实体**：

| 实体名 | API 路径 | 描述 | 目标统一表 |
|--------|----------|------|-----------|
| `employee` | /open-apis/ehr/v1/employees | 员工 | unified_contacts |
| `department` | /open-apis/contact/v3/departments | 部门 | - (元数据) |
| `approval` | /open-apis/approval/v4/instances | 审批实例 | unified_projects |

**配置结构**：
```python
{
    "base_url": "https://open.feishu.cn",
    "app_id": "应用ID",
    "app_secret": "应用密钥（加密存储）"
}
```

---

### 4. 禅道连接器

**注册名**：`zentao`

**认证方式**：Session Token
- 调用 `/api.php/v1/tokens` 获取 token
- 使用用户名 + 密码认证

**支持实体**：

| 实体名 | API 路径 | 描述 | 目标统一表 |
|--------|----------|------|-----------|
| `project` | /api.php/v1/projects | 项目 | unified_projects |
| `story` | /api.php/v1/stories | 需求 | unified_projects |
| `task` | /api.php/v1/tasks | 任务 | unified_projects |
| `bug` | /api.php/v1/bugs | Bug | unified_projects |

**配置结构**：
```python
{
    "base_url": "https://zentao.company.com",
    "username": "用户名",
    "password": "密码（加密存储）"
}
```

**注意**：因无实际 API 文档，先实现 mock 版本，预留真实调用结构。`_request()` 方法内部可切换 mock/real 模式。

---

### 5. 领星ERP连接器

**注册名**：`lingxing`

**认证方式**：HMAC 签名
- 每次请求计算签名：`HMAC-SHA256(app_secret, 请求参数排序拼接)`
- 签名放入请求头 `X-Ak-Sign`
- 不需要预先获取 token

**支持实体**：

| 实体名 | API 路径 | 描述 | 目标统一表 |
|--------|----------|------|-----------|
| `product` | /erp/sc/routing/data/local_inventory/productList | 商品 | unified_products |
| `order` | /erp/sc/routing/data/mws_orders/list | 订单 | unified_orders |
| `inventory` | /erp/sc/routing/data/local_inventory/list | 库存 | unified_inventory |
| `shipment` | /erp/sc/routing/data/shipment/list | 物流 | unified_orders |

**配置结构**：
```python
{
    "base_url": "https://openapi.lingxing.com",
    "app_id": "应用ID",
    "app_secret": "应用密钥（加密存储）"
}
```

---

## 字段映射策略

每个连接器完成后，需配置该连接器各实体到统一表的字段映射。

**映射记录存储**：`field_mappings` 表

**示例**（纷享销客 customer → unified_customers）：

| source_field | target_field | transform |
|--------------|--------------|-----------|
| name | name | - |
| phone | phone | - |
| email | email | - |
| industry | industry | - |
| createTime | created_at | date_format |

映射将在每个连接器实现时由用户提供实体字段信息后配置。

---

## 测试策略

### 单元测试（每个连接器）

1. **注册测试**：验证连接器已注册到全局注册表
2. **实体列表测试**：`list_entities()` 返回预期实体
3. **认证测试**：`connect()` 成功获取 token（mock HTTP）
4. **健康检查测试**：成功返回 healthy，失败返回 unhealthy
5. **拉取成功测试**：`pull()` 返回数据列表（mock）
6. **拉取失败测试**：API 错误时抛出 `ConnectorPullError`
7. **推送测试**：`push()` 返回 `PushResult`（mock）

### 测试文件命名

- `tests/test_connector_kingdee_plm.py`
- `tests/test_connector_fenxiangxiaoke.py`
- `tests/test_connector_feishu.py`
- `tests/test_connector_zentao.py`
- `tests/test_connector_lingxing.py`

---

## 实施顺序

1. **金蝶PLM** — 与已完成的金蝶ERP认证方式相近
2. **飞书** — OAuth2 标准化，文档完善
3. **纷享销客CRM** — 客户数据核心
4. **领星ERP** — HMAC 签名认证
5. **禅道** — mock 实现

每个连接器完成后：
- 实现连接器代码 + 测试
- 用户提供实体字段信息
- 配置字段映射
- 验证端到端数据流

---

## 验收标准

- [ ] 5个连接器全部实现并注册
- [ ] 每个连接器有 ≥7 个单元测试
- [ ] 所有测试通过（预计新增 35+ 测试）
- [ ] 每个连接器的字段映射已配置
- [ ] 数据能从外部系统拉取并写入统一表
