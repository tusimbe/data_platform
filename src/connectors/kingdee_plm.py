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
        url = (
            f"{self.config['base_url']}/k3cloud/"
            "Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc"
        )
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
        url = (
            f"{self.config['base_url']}/k3cloud/"
            "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc"
        )

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
        url = (
            f"{self.config['base_url']}/k3cloud/"
            "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Save.common.kdsvc"
        )

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
                    retry_after = int(
                        resp.headers.get("Retry-After", RETRY_BACKOFF[attempt])
                    )
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
