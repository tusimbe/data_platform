# src/connectors/zentao.py
"""禅道连接器（mock 版本，预留真实 API 结构）

禅道是一个开源项目管理系统，支持项目、需求、任务、Bug 等实体。

认证方式：Session Token via /api.php/v1/tokens
分页方式：limit + offset
"""
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
    """禅道连接器（mock 版本，预留真实 API 结构）
    
    使用 Session Token 认证，通过 /api.php/v1/tokens 获取。
    支持项目、需求、任务、Bug 等实体的读写操作。
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._token: str | None = None
        self._token_expires_at: float = 0
        self._client = httpx.Client(timeout=30.0)

    def connect(self) -> None:
        """获取 session token"""
        url = f"{self.config['base_url']}/api.php/v1/tokens"
        payload = {
            "account": self.config["username"],
            "password": self.config["password"],
        }
        result = self._request("POST", url, json=payload, skip_auth=True)
        if result.get("success"):
            self._token = result.get("token")
            # 禅道 token 通常24小时有效，提前1小时刷新
            self._token_expires_at = time.time() + 23 * 3600
        else:
            raise ConnectorPullError(f"禅道认证失败: {result.get('message', '未知错误')}")

    def disconnect(self) -> None:
        """断开连接，清除 token"""
        self._token = None
        self._token_expires_at = 0
        self._client.close()

    def _ensure_token(self) -> None:
        """确保 token 有效，过期则刷新"""
        if not self._token or time.time() >= self._token_expires_at:
            self.connect()

    def health_check(self) -> HealthStatus:
        """健康检查"""
        start = time.time()
        try:
            self._ensure_token()
            # 调用一个轻量 API 验证连接
            url = f"{self.config['base_url']}/api.php/v1/user"
            self._request("GET", url)
            latency = (time.time() - start) * 1000
            return HealthStatus(status="healthy", latency_ms=round(latency, 2))
        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthStatus(
                status="unhealthy", latency_ms=round(latency, 2), error=str(e)
            )

    def list_entities(self) -> list[EntityInfo]:
        """列出支持的实体"""
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
        """拉取禅道实体数据
        
        Args:
            entity: 实体类型 (project/story/task/bug)
            since: 增量同步起始时间
            filters: 额外过滤参数
            
        Returns:
            记录列表
            
        Raises:
            ConnectorPullError: 拉取失败时抛出
        """
        if entity not in ZENTAO_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        self._ensure_token()
        entity_config = ZENTAO_ENTITIES[entity]
        url = f"{self.config['base_url']}{entity_config['path']}"

        all_records = []
        offset = 0

        try:
            while True:
                params = {
                    "limit": DEFAULT_PAGE_SIZE,
                    "offset": offset,
                }
                
                if filters:
                    params.update(filters)
                    
                if since:
                    params["lastEditedDate[>]"] = since.isoformat()

                result = self._request("GET", url, params=params)
                
                if not result.get("success", True):
                    error_msg = result.get("message", "未知错误")
                    raise ConnectorPullError(f"禅道 API 错误: {error_msg}")

                list_key = entity_config["list_key"]
                records = result.get(list_key, [])
                all_records.extend(records)

                # 检查是否还有更多数据
                # 如果返回的数据少于 limit，表示已到最后一页
                if len(records) < DEFAULT_PAGE_SIZE:
                    break

                offset += DEFAULT_PAGE_SIZE

            return all_records
        except ConnectorPullError:
            raise
        except Exception as e:
            logger.error(f"禅道拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        """推送数据到禅道
        
        禅道支持通过 API 创建实体数据。
        
        Args:
            entity: 实体类型
            records: 要推送的记录列表
            
        Returns:
            PushResult 包含成功和失败计数
        """
        if entity not in ZENTAO_ENTITIES:
            raise ConnectorPushError(f"不支持的实体类型: {entity}")

        self._ensure_token()
        entity_config = ZENTAO_ENTITIES[entity]
        url = f"{self.config['base_url']}{entity_config['path']}"

        success_count = 0
        failure_count = 0
        failures = []

        for record in records:
            try:
                result = self._request("POST", url, json=record)
                
                if result.get("success", True):
                    success_count += 1
                else:
                    failure_count += 1
                    failures.append({
                        "record": record,
                        "error": result.get("message", "未知错误"),
                    })
            except Exception as e:
                failure_count += 1
                failures.append({
                    "record": record,
                    "error": str(e),
                })

        return PushResult(
            success_count=success_count,
            failure_count=failure_count,
            failures=failures,
        )

    def get_schema(self, entity: str) -> dict:
        """获取实体配置信息"""
        return ZENTAO_ENTITIES.get(entity, {})

    def _request(
        self, method: str, url: str, skip_auth: bool = False, **kwargs
    ) -> dict:
        """带重试的 HTTP 请求"""
        headers = kwargs.pop("headers", {})
        headers["Content-Type"] = "application/json"
        
        # 添加 token 认证（除非跳过）
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
