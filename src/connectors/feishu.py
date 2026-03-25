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

DEFAULT_PAGE_SIZE = 100

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
    """飞书连接器
    
    使用 OAuth2 tenant_access_token 认证，支持自动刷新过期 token。
    """

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
        """拉取飞书实体数据
        
        Args:
            entity: 实体类型 (employee/department/approval)
            since: 增量同步起始时间 (飞书 API 支持有限)
            filters: 额外过滤参数
            
        Returns:
            记录列表
            
        Raises:
            ConnectorPullError: 拉取失败时抛出
            
        Note:
            filter 参数由调用方预验证，本方法不做额外校验。
        """
        if entity not in FEISHU_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        self._ensure_token()
        entity_config = FEISHU_ENTITIES[entity]
        url = f"{self.config['base_url']}{entity_config['path']}"

        params = {"page_size": DEFAULT_PAGE_SIZE}
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
        """飞书大部分实体不支持写入，返回失败结果
        
        Args:
            entity: 实体类型
            records: 要推送的记录列表
            
        Returns:
            PushResult，所有记录标记为失败
        """
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
