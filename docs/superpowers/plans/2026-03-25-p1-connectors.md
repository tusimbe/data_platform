# P1 子项目4：剩余连接器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现剩余5个外部系统连接器（金蝶PLM、飞书、纷享销客CRM、领星ERP、禅道），使平台能够从这些系统拉取和推送数据。

**Architecture:** 每个连接器继承 `BaseConnector` 抽象基类，实现统一接口（connect/disconnect/health_check/pull/push/get_schema）。使用 `@register_connector` 装饰器注册到全局注册表。复用 P0 的重试机制、限流处理和字段映射服务。

**Tech Stack:** Python 3.11+, httpx, pytest, SQLAlchemy 2.0

**Spec:** `docs/superpowers/specs/2026-03-25-p1-connectors-design.md`

---

## 文件结构

### 新建文件

| 文件路径 | 职责 |
|----------|------|
| `src/connectors/kingdee_plm.py` | 金蝶PLM连接器 |
| `src/connectors/feishu.py` | 飞书连接器 |
| `src/connectors/fenxiangxiaoke.py` | 纷享销客CRM连接器 |
| `src/connectors/lingxing.py` | 领星ERP连接器 |
| `src/connectors/zentao.py` | 禅道连接器（mock） |
| `tests/test_connector_kingdee_plm.py` | 金蝶PLM测试 |
| `tests/test_connector_feishu.py` | 飞书测试 |
| `tests/test_connector_fenxiangxiaoke.py` | 纷享销客测试 |
| `tests/test_connector_lingxing.py` | 领星测试 |
| `tests/test_connector_zentao.py` | 禅道测试 |

### 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `src/connectors/__init__.py` | 导入新连接器 |

---

## Task 1: 金蝶PLM连接器

**Files:**
- Create: `src/connectors/kingdee_plm.py`
- Test: `tests/test_connector_kingdee_plm.py`

- [ ] **Step 1: 编写金蝶PLM连接器测试**

```python
# tests/test_connector_kingdee_plm.py
import pytest
from unittest.mock import patch, MagicMock

from src.connectors.kingdee_plm import KingdeePLMConnector
from src.connectors.base import (
    HealthStatus, EntityInfo, PushResult,
    ConnectorPullError, connector_registry,
)


@pytest.fixture
def plm_config():
    return {
        "base_url": "https://plm.kingdee.com",
        "acct_id": "test_acct",
        "username": "test_user",
        "password": "test_pass",
        "lcid": 2052,
    }


@pytest.fixture
def connector(plm_config):
    return KingdeePLMConnector(config=plm_config)


def test_kingdee_plm_registered():
    """金蝶PLM连接器应已注册到全局注册表"""
    cls = connector_registry.get("kingdee_plm")
    assert cls is KingdeePLMConnector


def test_kingdee_plm_list_entities(connector):
    """应返回支持的实体列表"""
    entities = connector.list_entities()
    assert len(entities) >= 4
    names = [e.name for e in entities]
    assert "product" in names
    assert "material" in names
    assert "bom" in names


def test_kingdee_plm_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"Result": {"ResponseStatus": {"IsSuccess": True}}}
        result = connector.health_check()
        assert result.status == "healthy"
        assert result.latency_ms is not None


def test_kingdee_plm_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"
        assert "Connection refused" in result.error


def test_kingdee_plm_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    mock_response = [
        {"FNumber": "P-001", "FName": "产品A", "FDescription": "描述"},
        {"FNumber": "P-002", "FName": "产品B", "FDescription": "描述"},
    ]
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="product")
        assert len(records) == 2
        assert records[0]["FNumber"] == "P-001"


def test_kingdee_plm_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("API Error 500")
        with pytest.raises(ConnectorPullError):
            connector.pull(entity="product")


def test_kingdee_plm_connect_gets_token(connector):
    """connect() 应获取会话令牌"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {
            "KDToken": "mock-plm-token-123",
            "IsSuccessByAPI": True,
        }
        connector.connect()
        assert connector._token == "mock-plm-token-123"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_connector_kingdee_plm.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现金蝶PLM连接器**

```python
# src/connectors/kingdee_plm.py
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

# 金蝶PLM支持的实体及对应 API FormId
KINGDEE_PLM_ENTITIES = {
    "product": {"form_id": "PLM_Product", "description": "产品主数据"},
    "material": {"form_id": "PLM_Material", "description": "物料主数据"},
    "bom": {"form_id": "PLM_BOM", "description": "物料清单"},
    "change_order": {"form_id": "PLM_ECO", "description": "工程变更单"},
}

MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


@register_connector("kingdee_plm")
class KingdeePLMConnector(BaseConnector):
    """金蝶PLM连接器"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._token: str | None = None
        self._client = httpx.Client(timeout=30.0)

    def connect(self) -> None:
        """通过金蝶 API 获取会话令牌"""
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
            for name, meta in KINGDEE_PLM_ENTITIES.items()
        ]

    def pull(
        self,
        entity: str,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        if entity not in KINGDEE_PLM_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        form_id = KINGDEE_PLM_ENTITIES[entity]["form_id"]
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
            logger.error(f"金蝶PLM拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        if entity not in KINGDEE_PLM_ENTITIES:
            raise ConnectorPushError(f"不支持的实体类型: {entity}")

        form_id = KINGDEE_PLM_ENTITIES[entity]["form_id"]
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
                    "record": record.get("FNumber", "unknown"),
                    "error": str(e),
                })

        return PushResult(
            success_count=success_count,
            failure_count=failure_count,
            failures=failures,
        )

    def get_schema(self, entity: str) -> dict:
        """返回实体的字段结构（简化实现）"""
        return KINGDEE_PLM_ENTITIES.get(entity, {})

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

Run: `cd data_platform && python -m pytest tests/test_connector_kingdee_plm.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 实现金蝶PLM连接器

支持 product/material/bom/change_order 实体，
复用金蝶ERP认证模式，带重试和限流处理。"
```

---

## Task 2: 飞书连接器

**Files:**
- Create: `src/connectors/feishu.py`
- Test: `tests/test_connector_feishu.py`

- [ ] **Step 1: 编写飞书连接器测试**

```python
# tests/test_connector_feishu.py
import pytest
from unittest.mock import patch, MagicMock
import time

from src.connectors.feishu import FeishuConnector
from src.connectors.base import (
    HealthStatus, EntityInfo, PushResult,
    ConnectorPullError, connector_registry,
)


@pytest.fixture
def feishu_config():
    return {
        "base_url": "https://open.feishu.cn",
        "app_id": "cli_test_app_id",
        "app_secret": "test_app_secret",
    }


@pytest.fixture
def connector(feishu_config):
    return FeishuConnector(config=feishu_config)


def test_feishu_registered():
    """飞书连接器应已注册到全局注册表"""
    cls = connector_registry.get("feishu")
    assert cls is FeishuConnector


def test_feishu_list_entities(connector):
    """应返回支持的实体列表"""
    entities = connector.list_entities()
    assert len(entities) >= 3
    names = [e.name for e in entities]
    assert "employee" in names
    assert "department" in names
    assert "approval" in names


def test_feishu_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"code": 0}
        result = connector.health_check()
        assert result.status == "healthy"


def test_feishu_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"


def test_feishu_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    mock_response = {
        "code": 0,
        "data": {
            "items": [
                {"user_id": "ou_001", "name": "张三", "department_id": "d001"},
                {"user_id": "ou_002", "name": "李四", "department_id": "d001"},
            ]
        }
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="employee")
        assert len(records) == 2
        assert records[0]["user_id"] == "ou_001"


def test_feishu_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("API Error")
        with pytest.raises(ConnectorPullError):
            connector.pull(entity="employee")


def test_feishu_connect_gets_token(connector):
    """connect() 应获取 tenant_access_token"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {
            "code": 0,
            "tenant_access_token": "t-test-token-123",
            "expire": 7200,
        }
        connector.connect()
        assert connector._token == "t-test-token-123"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_connector_feishu.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现飞书连接器**

```python
# src/connectors/feishu.py
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

# 飞书支持的实体及对应 API 路径
FEISHU_ENTITIES = {
    "employee": {
        "path": "/open-apis/ehr/v1/employees",
        "description": "员工",
        "list_key": "items",
    },
    "department": {
        "path": "/open-apis/contact/v3/departments",
        "description": "部门",
        "list_key": "items",
    },
    "approval": {
        "path": "/open-apis/approval/v4/instances",
        "description": "审批实例",
        "list_key": "items",
    },
}

MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


@register_connector("feishu")
class FeishuConnector(BaseConnector):
    """飞书连接器"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._client = httpx.Client(timeout=30.0)

    def connect(self) -> None:
        """获取 tenant_access_token"""
        url = f"{self.config['base_url']}/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.config["app_id"],
            "app_secret": self.config["app_secret"],
        }
        result = self._request("POST", url, json=payload, skip_auth=True)
        if result.get("code") == 0:
            self._token = result.get("tenant_access_token")
            expire = result.get("expire", 7200)
            self._token_expires_at = time.time() + expire - 300  # 提前5分钟刷新
        else:
            raise ConnectorPullError(f"飞书认证失败: {result}")

    def disconnect(self) -> None:
        self._token = None
        self._token_expires_at = 0
        self._client.close()

    def _ensure_token(self) -> None:
        """确保 token 有效，过期则刷新"""
        if not self._token or time.time() >= self._token_expires_at:
            self.connect()

    def health_check(self) -> HealthStatus:
        start = time.time()
        try:
            self._ensure_token()
            # 调用一个轻量 API 验证连接
            url = f"{self.config['base_url']}/open-apis/contact/v3/departments/0"
            self._request("GET", url)
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
            for name, meta in FEISHU_ENTITIES.items()
        ]

    def pull(
        self,
        entity: str,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        if entity not in FEISHU_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        self._ensure_token()
        entity_config = FEISHU_ENTITIES[entity]
        url = f"{self.config['base_url']}{entity_config['path']}"

        params = {"page_size": 100}
        if filters:
            params.update(filters)

        try:
            result = self._request("GET", url, params=params)
            if result.get("code") != 0:
                raise ConnectorPullError(f"飞书 API 错误: {result.get('msg')}")
            data = result.get("data", {})
            return data.get(entity_config["list_key"], [])
        except ConnectorPullError:
            raise
        except Exception as e:
            logger.error(f"飞书拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        """飞书大部分实体不支持写入，返回空结果"""
        return PushResult(success_count=0, failure_count=len(records), failures=[
            {"record": r, "error": "飞书不支持此实体的写入"} for r in records
        ])

    def get_schema(self, entity: str) -> dict:
        return FEISHU_ENTITIES.get(entity, {})

    def _request(
        self, method: str, url: str, skip_auth: bool = False, **kwargs
    ) -> dict:
        """带重试的 HTTP 请求"""
        headers = kwargs.pop("headers", {})
        if not skip_auth and self._token:
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

Run: `cd data_platform && python -m pytest tests/test_connector_feishu.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 实现飞书连接器

支持 employee/department/approval 实体，
OAuth2 tenant_access_token 认证，自动刷新过期 token。"
```

---

## Task 3: 纷享销客CRM连接器

**Files:**
- Create: `src/connectors/fenxiangxiaoke.py`
- Test: `tests/test_connector_fenxiangxiaoke.py`

- [ ] **Step 1: 编写纷享销客连接器测试**

```python
# tests/test_connector_fenxiangxiaoke.py
import pytest
from unittest.mock import patch, MagicMock

from src.connectors.fenxiangxiaoke import FenxiangxiaokeConnector
from src.connectors.base import (
    HealthStatus, EntityInfo, PushResult,
    ConnectorPullError, connector_registry,
)


@pytest.fixture
def fxiaoke_config():
    return {
        "base_url": "https://open.fxiaoke.com",
        "app_id": "test_app_id",
        "app_secret": "test_app_secret",
        "permanent_code": "test_permanent_code",
    }


@pytest.fixture
def connector(fxiaoke_config):
    return FenxiangxiaokeConnector(config=fxiaoke_config)


def test_fenxiangxiaoke_registered():
    """纷享销客连接器应已注册到全局注册表"""
    cls = connector_registry.get("fenxiangxiaoke")
    assert cls is FenxiangxiaokeConnector


def test_fenxiangxiaoke_list_entities(connector):
    """应返回支持的实体列表"""
    entities = connector.list_entities()
    assert len(entities) >= 4
    names = [e.name for e in entities]
    assert "customer" in names
    assert "contact" in names
    assert "opportunity" in names


def test_fenxiangxiaoke_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"errorCode": 0}
        result = connector.health_check()
        assert result.status == "healthy"


def test_fenxiangxiaoke_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"


def test_fenxiangxiaoke_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    mock_response = {
        "errorCode": 0,
        "data": {
            "dataList": [
                {"_id": "c001", "name": "客户A", "phone": "13800000001"},
                {"_id": "c002", "name": "客户B", "phone": "13800000002"},
            ]
        }
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="customer")
        assert len(records) == 2
        assert records[0]["name"] == "客户A"


def test_fenxiangxiaoke_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("API Error")
        with pytest.raises(ConnectorPullError):
            connector.pull(entity="customer")


def test_fenxiangxiaoke_connect_gets_token(connector):
    """connect() 应获取 access_token"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {
            "errorCode": 0,
            "corpAccessToken": "test-access-token-123",
            "expiresIn": 7200,
        }
        connector.connect()
        assert connector._token == "test-access-token-123"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_connector_fenxiangxiaoke.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现纷享销客连接器**

```python
# src/connectors/fenxiangxiaoke.py
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

# 纷享销客支持的实体及对应 API 路径
FXIAOKE_ENTITIES = {
    "customer": {
        "path": "/cgi/crm/custom/v2/list",
        "description": "客户",
        "list_key": "dataList",
    },
    "contact": {
        "path": "/cgi/crm/contact/list",
        "description": "联系人",
        "list_key": "dataList",
    },
    "opportunity": {
        "path": "/cgi/crm/opportunity/list",
        "description": "商机",
        "list_key": "dataList",
    },
    "contract": {
        "path": "/cgi/crm/contract/list",
        "description": "合同",
        "list_key": "dataList",
    },
}

MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


@register_connector("fenxiangxiaoke")
class FenxiangxiaokeConnector(BaseConnector):
    """纷享销客CRM连接器"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._client = httpx.Client(timeout=30.0)

    def connect(self) -> None:
        """获取 corpAccessToken"""
        url = f"{self.config['base_url']}/cgi/corpAccessToken/get/V2"
        payload = {
            "appId": self.config["app_id"],
            "appSecret": self.config["app_secret"],
            "permanentCode": self.config["permanent_code"],
        }
        result = self._request("POST", url, json=payload, skip_auth=True)
        if result.get("errorCode") == 0:
            self._token = result.get("corpAccessToken")
            expire = result.get("expiresIn", 7200)
            self._token_expires_at = time.time() + expire - 300
        else:
            raise ConnectorPullError(f"纷享销客认证失败: {result}")

    def disconnect(self) -> None:
        self._token = None
        self._token_expires_at = 0
        self._client.close()

    def _ensure_token(self) -> None:
        """确保 token 有效，过期则刷新"""
        if not self._token or time.time() >= self._token_expires_at:
            self.connect()

    def health_check(self) -> HealthStatus:
        start = time.time()
        try:
            self._ensure_token()
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
            for name, meta in FXIAOKE_ENTITIES.items()
        ]

    def pull(
        self,
        entity: str,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        if entity not in FXIAOKE_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        self._ensure_token()
        entity_config = FXIAOKE_ENTITIES[entity]
        url = f"{self.config['base_url']}{entity_config['path']}"

        payload = {
            "corpAccessToken": self._token,
            "corpId": self.config.get("corp_id", ""),
            "currentOpenUserId": self.config.get("user_id", ""),
            "data": {
                "dataObjectApiName": entity,
                "pageSize": 100,
                "pageNumber": 1,
            }
        }

        if since:
            payload["data"]["filters"] = [{
                "field_name": "last_modified_time",
                "field_values": [since.strftime("%Y-%m-%d %H:%M:%S")],
                "operator": "GTE",
            }]

        try:
            result = self._request("POST", url, json=payload)
            if result.get("errorCode") != 0:
                raise ConnectorPullError(f"纷享销客 API 错误: {result.get('errorMessage')}")
            data = result.get("data", {})
            return data.get(entity_config["list_key"], [])
        except ConnectorPullError:
            raise
        except Exception as e:
            logger.error(f"纷享销客拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        if entity not in FXIAOKE_ENTITIES:
            raise ConnectorPushError(f"不支持的实体类型: {entity}")

        self._ensure_token()
        url = f"{self.config['base_url']}/cgi/crm/custom/v2/data/create"

        success_count = 0
        failure_count = 0
        failures = []

        for record in records:
            try:
                payload = {
                    "corpAccessToken": self._token,
                    "corpId": self.config.get("corp_id", ""),
                    "currentOpenUserId": self.config.get("user_id", ""),
                    "data": {
                        "dataObjectApiName": entity,
                        "objectData": record,
                    }
                }
                result = self._request("POST", url, json=payload)
                if result.get("errorCode") == 0:
                    success_count += 1
                else:
                    failure_count += 1
                    failures.append({"record": record, "error": result.get("errorMessage")})
            except Exception as e:
                failure_count += 1
                failures.append({"record": record, "error": str(e)})

        return PushResult(
            success_count=success_count,
            failure_count=failure_count,
            failures=failures,
        )

    def get_schema(self, entity: str) -> dict:
        return FXIAOKE_ENTITIES.get(entity, {})

    def _request(
        self, method: str, url: str, skip_auth: bool = False, **kwargs
    ) -> dict:
        """带重试的 HTTP 请求"""
        headers = kwargs.pop("headers", {})
        headers["Content-Type"] = "application/json"

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

Run: `cd data_platform && python -m pytest tests/test_connector_fenxiangxiaoke.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 实现纷享销客CRM连接器

支持 customer/contact/opportunity/contract 实体，
OAuth2 corpAccessToken 认证，自动刷新过期 token。"
```

---

## Task 4: 领星ERP连接器

**Files:**
- Create: `src/connectors/lingxing.py`
- Test: `tests/test_connector_lingxing.py`

- [ ] **Step 1: 编写领星ERP连接器测试**

```python
# tests/test_connector_lingxing.py
import pytest
from unittest.mock import patch, MagicMock

from src.connectors.lingxing import LingxingConnector
from src.connectors.base import (
    HealthStatus, EntityInfo, PushResult,
    ConnectorPullError, connector_registry,
)


@pytest.fixture
def lingxing_config():
    return {
        "base_url": "https://openapi.lingxing.com",
        "app_id": "test_app_id",
        "app_secret": "test_app_secret",
    }


@pytest.fixture
def connector(lingxing_config):
    return LingxingConnector(config=lingxing_config)


def test_lingxing_registered():
    """领星ERP连接器应已注册到全局注册表"""
    cls = connector_registry.get("lingxing")
    assert cls is LingxingConnector


def test_lingxing_list_entities(connector):
    """应返回支持的实体列表"""
    entities = connector.list_entities()
    assert len(entities) >= 4
    names = [e.name for e in entities]
    assert "product" in names
    assert "order" in names
    assert "inventory" in names


def test_lingxing_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"code": 0, "msg": "success"}
        result = connector.health_check()
        assert result.status == "healthy"


def test_lingxing_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"


def test_lingxing_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    mock_response = {
        "code": 0,
        "data": [
            {"sku": "SKU-001", "title": "商品A", "quantity": 100},
            {"sku": "SKU-002", "title": "商品B", "quantity": 200},
        ]
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="product")
        assert len(records) == 2
        assert records[0]["sku"] == "SKU-001"


def test_lingxing_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("API Error")
        with pytest.raises(ConnectorPullError):
            connector.pull(entity="product")


def test_lingxing_signature_generation(connector):
    """应能正确生成 HMAC 签名"""
    # 验证签名函数存在且可调用
    signature = connector._generate_signature({"timestamp": "1234567890"})
    assert signature is not None
    assert len(signature) > 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_connector_lingxing.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现领星ERP连接器**

```python
# src/connectors/lingxing.py
import time
import hmac
import hashlib
import logging
from datetime import datetime
from urllib.parse import urlencode

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

# 领星ERP支持的实体及对应 API 路径
LINGXING_ENTITIES = {
    "product": {
        "path": "/erp/sc/routing/data/local_inventory/productList",
        "description": "商品",
    },
    "order": {
        "path": "/erp/sc/routing/data/mws_orders/list",
        "description": "订单",
    },
    "inventory": {
        "path": "/erp/sc/routing/data/local_inventory/list",
        "description": "库存",
    },
    "shipment": {
        "path": "/erp/sc/routing/data/shipment/list",
        "description": "物流",
    },
}

MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


@register_connector("lingxing")
class LingxingConnector(BaseConnector):
    """领星ERP连接器（HMAC签名认证）"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = httpx.Client(timeout=30.0)

    def connect(self) -> None:
        """领星使用 HMAC 签名，无需预先获取 token"""
        pass

    def disconnect(self) -> None:
        self._client.close()

    def _generate_signature(self, params: dict) -> str:
        """生成 HMAC-SHA256 签名"""
        # 参数按 key 排序后拼接
        sorted_params = sorted(params.items())
        sign_string = urlencode(sorted_params)
        
        signature = hmac.new(
            self.config["app_secret"].encode("utf-8"),
            sign_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        return signature

    def health_check(self) -> HealthStatus:
        start = time.time()
        try:
            # 调用一个轻量 API 验证连接
            self.pull(entity="product")
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
            for name, meta in LINGXING_ENTITIES.items()
        ]

    def pull(
        self,
        entity: str,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        if entity not in LINGXING_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        entity_config = LINGXING_ENTITIES[entity]
        url = f"{self.config['base_url']}{entity_config['path']}"

        params = {
            "app_id": self.config["app_id"],
            "timestamp": str(int(time.time())),
            "page": 1,
            "size": 100,
        }
        
        if since:
            params["start_time"] = since.strftime("%Y-%m-%d %H:%M:%S")
        
        if filters:
            params.update(filters)

        try:
            result = self._request("POST", url, params=params)
            if result.get("code") != 0:
                raise ConnectorPullError(f"领星 API 错误: {result.get('msg')}")
            return result.get("data", [])
        except ConnectorPullError:
            raise
        except Exception as e:
            logger.error(f"领星拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        """领星ERP大部分场景是只读，推送返回空结果"""
        return PushResult(success_count=0, failure_count=len(records), failures=[
            {"record": r, "error": "领星ERP不支持此实体的写入"} for r in records
        ])

    def get_schema(self, entity: str) -> dict:
        return LINGXING_ENTITIES.get(entity, {})

    def _request(self, method: str, url: str, params: dict = None, **kwargs) -> dict:
        """带 HMAC 签名和重试的 HTTP 请求"""
        params = params or {}
        signature = self._generate_signature(params)
        
        headers = kwargs.pop("headers", {})
        headers["X-Ak-Sign"] = signature
        headers["X-Ak-App-Id"] = self.config["app_id"]
        headers["Content-Type"] = "application/json"

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.request(
                    method, url, headers=headers, json=params, **kwargs
                )

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

Run: `cd data_platform && python -m pytest tests/test_connector_lingxing.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 实现领星ERP连接器

支持 product/order/inventory/shipment 实体，
HMAC-SHA256 签名认证，每次请求计算签名。"
```

---

## Task 5: 禅道连接器（mock）

**Files:**
- Create: `src/connectors/zentao.py`
- Test: `tests/test_connector_zentao.py`

- [ ] **Step 1: 编写禅道连接器测试**

```python
# tests/test_connector_zentao.py
import pytest
from unittest.mock import patch, MagicMock

from src.connectors.zentao import ZentaoConnector
from src.connectors.base import (
    HealthStatus, EntityInfo, PushResult,
    ConnectorPullError, connector_registry,
)


@pytest.fixture
def zentao_config():
    return {
        "base_url": "https://zentao.company.com",
        "username": "admin",
        "password": "admin123",
    }


@pytest.fixture
def connector(zentao_config):
    return ZentaoConnector(config=zentao_config)


def test_zentao_registered():
    """禅道连接器应已注册到全局注册表"""
    cls = connector_registry.get("zentao")
    assert cls is ZentaoConnector


def test_zentao_list_entities(connector):
    """应返回支持的实体列表"""
    entities = connector.list_entities()
    assert len(entities) >= 4
    names = [e.name for e in entities]
    assert "project" in names
    assert "story" in names
    assert "task" in names
    assert "bug" in names


def test_zentao_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"status": "success"}
        result = connector.health_check()
        assert result.status == "healthy"


def test_zentao_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"


def test_zentao_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    mock_response = {
        "projects": [
            {"id": 1, "name": "项目A", "status": "doing"},
            {"id": 2, "name": "项目B", "status": "done"},
        ]
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="project")
        assert len(records) == 2
        assert records[0]["name"] == "项目A"


def test_zentao_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("API Error")
        with pytest.raises(ConnectorPullError):
            connector.pull(entity="project")


def test_zentao_connect_gets_token(connector):
    """connect() 应获取 session token"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"token": "zentao-session-token-123"}
        connector.connect()
        assert connector._token == "zentao-session-token-123"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd data_platform && python -m pytest tests/test_connector_zentao.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现禅道连接器（mock 版本）**

```python
# src/connectors/zentao.py
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

# 禅道支持的实体及对应 API 路径
ZENTAO_ENTITIES = {
    "project": {
        "path": "/api.php/v1/projects",
        "description": "项目",
        "list_key": "projects",
    },
    "story": {
        "path": "/api.php/v1/stories",
        "description": "需求",
        "list_key": "stories",
    },
    "task": {
        "path": "/api.php/v1/tasks",
        "description": "任务",
        "list_key": "tasks",
    },
    "bug": {
        "path": "/api.php/v1/bugs",
        "description": "Bug",
        "list_key": "bugs",
    },
}

MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


@register_connector("zentao")
class ZentaoConnector(BaseConnector):
    """禅道连接器（mock 版本，预留真实 API 结构）"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._token: str | None = None
        self._client = httpx.Client(timeout=30.0)

    def connect(self) -> None:
        """获取 session token"""
        url = f"{self.config['base_url']}/api.php/v1/tokens"
        payload = {
            "account": self.config["username"],
            "password": self.config["password"],
        }
        result = self._request("POST", url, json=payload, skip_auth=True)
        self._token = result.get("token", "")

    def disconnect(self) -> None:
        self._token = None
        self._client.close()

    def health_check(self) -> HealthStatus:
        start = time.time()
        try:
            url = f"{self.config['base_url']}/api.php/v1/projects"
            self._request("GET", url)
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
            for name, meta in ZENTAO_ENTITIES.items()
        ]

    def pull(
        self,
        entity: str,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        if entity not in ZENTAO_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        entity_config = ZENTAO_ENTITIES[entity]
        url = f"{self.config['base_url']}{entity_config['path']}"

        params = {"limit": 100}
        if filters:
            params.update(filters)

        try:
            result = self._request("GET", url, params=params)
            return result.get(entity_config["list_key"], [])
        except Exception as e:
            logger.error(f"禅道拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        if entity not in ZENTAO_ENTITIES:
            raise ConnectorPushError(f"不支持的实体类型: {entity}")

        entity_config = ZENTAO_ENTITIES[entity]
        url = f"{self.config['base_url']}{entity_config['path']}"

        success_count = 0
        failure_count = 0
        failures = []

        for record in records:
            try:
                self._request("POST", url, json=record)
                success_count += 1
            except Exception as e:
                failure_count += 1
                failures.append({"record": record, "error": str(e)})

        return PushResult(
            success_count=success_count,
            failure_count=failure_count,
            failures=failures,
        )

    def get_schema(self, entity: str) -> dict:
        return ZENTAO_ENTITIES.get(entity, {})

    def _request(
        self, method: str, url: str, skip_auth: bool = False, **kwargs
    ) -> dict:
        """带重试的 HTTP 请求"""
        headers = kwargs.pop("headers", {})
        if not skip_auth and self._token:
            headers["Token"] = self._token

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

Run: `cd data_platform && python -m pytest tests/test_connector_zentao.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat: 实现禅道连接器（mock 版本）

支持 project/story/task/bug 实体，
Session Token 认证，预留真实 API 调用结构。"
```

---

## Task 6: 更新连接器包导出

**Files:**
- Modify: `src/connectors/__init__.py`

- [ ] **Step 1: 更新 `__init__.py` 导入所有连接器**

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

# 导入所有连接器以触发注册
from src.connectors.kingdee_erp import KingdeeERPConnector  # noqa: F401
from src.connectors.kingdee_plm import KingdeePLMConnector  # noqa: F401
from src.connectors.feishu import FeishuConnector  # noqa: F401
from src.connectors.fenxiangxiaoke import FenxiangxiaokeConnector  # noqa: F401
from src.connectors.lingxing import LingxingConnector  # noqa: F401
from src.connectors.zentao import ZentaoConnector  # noqa: F401
```

- [ ] **Step 2: 运行全部测试确认通过**

Run: `cd data_platform && python -m pytest -v`
Expected: 全部通过（37 + 35 = 72 测试）

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "chore: 更新连接器包导出，注册所有连接器"
```

---

## 完成检查

执行完所有 Task 后，项目应具备：

1. **5 个新连接器**：kingdee_plm, feishu, fenxiangxiaoke, lingxing, zentao
2. **每个连接器 7 个测试**：共 35 个新测试
3. **全部测试通过**：约 72 个（P0 的 37 + P1 的 35）
4. **所有连接器已注册**：`connector_registry.list_types()` 返回 6 个类型

验证命令:

```bash
cd data_platform && python -m pytest -v --tb=short
cd data_platform && python -c "from src.connectors import connector_registry; print(connector_registry.list_types())"
```

Expected output:
```
['kingdee_erp', 'kingdee_plm', 'feishu', 'fenxiangxiaoke', 'lingxing', 'zentao']
```
