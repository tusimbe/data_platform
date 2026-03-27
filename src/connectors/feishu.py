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
)

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 100
MAX_PAGES = 1000

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
        "page_size": 50,  # 部门 API 最大 page_size=50, 超过返回空
        "default_params": {
            "parent_department_id": "0",
            "fetch_child": "true",
        },
    },
    "approval": {
        "path": "/open-apis/approval/v4/instances",
        "detail_path": "/open-apis/approval/v4/instances/{instance_id}",
        "description": "审批实例",
        "list_key": "instance_code_list",
        "page_size": 100,
    },
}

_APPROVAL_MAX_RANGE_MS = 30 * 24 * 3600 * 1000
_APPROVAL_DEFAULT_LOOKBACK_DAYS = 90
_DETAIL_BATCH_SIZE = 50


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
        resp = self._client.request("POST", url, json=payload)
        resp.raise_for_status()
        result = resp.json()
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
            return HealthStatus(status="unhealthy", latency_ms=round(latency, 2), error=str(e))

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

        if entity == "approval":
            return self._pull_approvals(since, filters)

        entity_config = FEISHU_ENTITIES[entity]
        url = f"{self.config['base_url']}{entity_config['path']}"

        all_records: list[dict] = []
        page_token = None
        page_count = 0

        try:
            while True:
                page_count += 1
                if page_count > MAX_PAGES:
                    logger.warning(f"Reached max page limit ({MAX_PAGES}) for entity={entity}")
                    break

                page_size = entity_config.get("page_size", DEFAULT_PAGE_SIZE)
                params: dict = {"page_size": page_size}
                default_params = entity_config.get("default_params")
                if default_params:
                    params.update(default_params)
                if page_token:
                    params["page_token"] = page_token
                if filters:
                    params.update(filters)

                result = self._request("GET", url, params=params)
                if result.get("code") != 0:
                    raise ConnectorPullError(f"飞书 API 错误: {result.get('msg')}")

                data = result.get("data", {})
                records = data.get(entity_config["list_key"], [])
                all_records.extend(records)

                page_token = data.get("page_token")
                if not page_token:
                    break

            return all_records
        except ConnectorPullError:
            raise
        except Exception as e:
            logger.error(f"飞书拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def _pull_approvals(
        self,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        filters = filters or {}
        approval_code = filters.get("approval_code") or self.config.get("approval_code")
        if not approval_code:
            raise ConnectorPullError(
                "approval_code is required — set it in connector auth_config or pass via filters"
            )

        now_ms = int(time.time() * 1000)
        if since:
            start_ms = int(since.timestamp() * 1000)
        else:
            start_ms = now_ms - _APPROVAL_DEFAULT_LOOKBACK_DAYS * 86400 * 1000

        entity_config = FEISHU_ENTITIES["approval"]
        list_url = f"{self.config['base_url']}{entity_config['path']}"

        all_codes: list[str] = []
        try:
            chunk_start = start_ms
            while chunk_start < now_ms:
                chunk_end = min(chunk_start + _APPROVAL_MAX_RANGE_MS, now_ms)
                page_token = None

                while True:
                    params: dict = {
                        "approval_code": approval_code,
                        "start_time": str(chunk_start),
                        "end_time": str(chunk_end),
                        "page_size": entity_config.get("page_size", DEFAULT_PAGE_SIZE),
                    }
                    if page_token:
                        params["page_token"] = page_token

                    result = self._request("GET", list_url, params=params)
                    if result.get("code") != 0:
                        raise ConnectorPullError(f"飞书 API 错误: {result.get('msg')}")

                    data = result.get("data", {})
                    codes = data.get("instance_code_list", [])
                    all_codes.extend(codes)

                    page_token = data.get("page_token")
                    if not page_token:
                        break

                chunk_start = chunk_end

            logger.info(f"Approval list done: {len(all_codes)} instance codes")

            detail_tpl = f"{self.config['base_url']}{entity_config['detail_path']}"
            all_records: list[dict] = []
            for i in range(0, len(all_codes), _DETAIL_BATCH_SIZE):
                batch = all_codes[i : i + _DETAIL_BATCH_SIZE]
                for code in batch:
                    url = detail_tpl.format(instance_id=code)
                    result = self._request("GET", url)
                    if result.get("code") == 0:
                        all_records.append(result["data"])
                    else:
                        logger.warning(f"Failed to fetch approval {code}: {result.get('msg')}")

                logger.info(f"Approval details: {len(all_records)}/{len(all_codes)} fetched")

            return all_records
        except ConnectorPullError:
            raise
        except Exception as e:
            logger.error(f"飞书审批拉取失败: {e}")
            raise ConnectorPullError(f"拉取 approval 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        """飞书大部分实体不支持写入，返回失败结果

        Args:
            entity: 实体类型
            records: 要推送的记录列表

        Returns:
            PushResult，所有记录标记为失败
        """
        return PushResult(
            success_count=0,
            failure_count=len(records),
            failures=[{"record": r, "error": "飞书不支持此实体的写入"} for r in records],
        )

    def get_schema(self, entity: str) -> dict:
        return FEISHU_ENTITIES.get(entity, {})

    def _prepare_request(self, method: str, url: str, headers: dict, kwargs: dict) -> None:
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
