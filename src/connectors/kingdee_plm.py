# src/connectors/kingdee_plm.py
import time
import logging
import re
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

DEFAULT_PAGE_LIMIT = 2000
MAX_PAGES = 500
_SAFE_FILTER_VALUE = re.compile(r"^[\w\s\-\.:/]+$")


@register_connector("kingdee_plm")
class KingdeePLMConnector(BaseConnector):
    """金蝶PLM连接器"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._token: str | None = None
        self._client = httpx.Client(timeout=30.0)

    @staticmethod
    def _sanitize_filter_value(value: str) -> str:
        str_val = str(value)
        if not _SAFE_FILTER_VALUE.match(str_val):
            raise ConnectorPullError("Invalid filter value: contains unsafe characters")
        return str_val

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
            return HealthStatus(status="unhealthy", latency_ms=round(latency, 2), error=str(e))

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
        """
        从金蝶PLM拉取指定实体的数据。

        Args:
            entity: 实体类型 (product/material/bom/change_order)
            since: 增量同步起始时间，仅拉取该时间后修改的记录
            filters: 额外过滤条件字典

        Returns:
            记录列表

        Raises:
            ConnectorPullError: 实体类型不支持或API调用失败

        Note:
            filter值会在本方法中执行白名单校验以防止注入。
        """
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
            extra = " AND ".join(
                f"{self._sanitize_filter_value(k)} = '{self._sanitize_filter_value(v)}'"
                for k, v in filters.items()
            )
            filter_string = f"{filter_string} AND {extra}" if filter_string else extra

        try:
            all_records = []
            start_row = 0
            page_count = 0

            while True:
                page_count += 1
                if page_count > MAX_PAGES:
                    logger.warning(f"Reached max page limit ({MAX_PAGES}) for entity={entity}")
                    break

                payload = {
                    "FormId": form_id,
                    "FieldKeys": "",
                    "FilterString": filter_string,
                    "OrderString": "",
                    "TopRowCount": 0,
                    "StartRow": start_row,
                    "Limit": DEFAULT_PAGE_LIMIT,
                }

                result = self._request("POST", url, json=payload)
                batch = result if isinstance(result, list) else []
                all_records.extend(batch)

                if len(batch) < DEFAULT_PAGE_LIMIT:
                    break

                start_row += DEFAULT_PAGE_LIMIT

            return all_records
        except Exception as e:
            logger.error(f"金蝶PLM拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        """
        推送记录到金蝶PLM。

        Args:
            entity: 实体类型 (product/material/bom/change_order)
            records: 待推送的记录列表

        Returns:
            PushResult: 包含成功/失败计数和失败详情

        Raises:
            ConnectorPushError: 实体类型不支持
        """
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
                logger.warning(
                    f"Failed to push {entity} record {record.get('FNumber', 'unknown')}: {e}"
                )
                failures.append(
                    {
                        "record": record.get("FNumber", "unknown"),
                        "error": str(e),
                    }
                )

        if failure_count > 0:
            logger.warning(f"Push {entity}: {failure_count}/{len(records)} records failed")

        return PushResult(
            success_count=success_count,
            failure_count=failure_count,
            failures=failures,
        )

    def get_schema(self, entity: str) -> dict:
        """返回实体的字段结构（简化实现）"""
        return KINGDEE_PLM_ENTITIES.get(entity, {})

    def _prepare_request(self, method: str, url: str, headers: dict, kwargs: dict) -> None:
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
