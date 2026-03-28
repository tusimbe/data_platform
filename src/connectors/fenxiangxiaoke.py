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

DEFAULT_PAGE_SIZE = 100
MAX_PAGES = 1000

# 纷享销客支持的实体及对应 API 路径
# 标准对象使用 /cgi/crm/v2/data/query
# 自定义对象 (__c 后缀) 使用 /cgi/crm/custom/v2/data/query
FXIAOKE_QUERY_PATH = "/cgi/crm/v2/data/query"
FXIAOKE_CUSTOM_QUERY_PATH = "/cgi/crm/custom/v2/data/query"
FXIAOKE_CREATE_PATH = "/cgi/crm/v2/data/create"

FXIAOKE_ENTITIES = {
    "customer": {
        "description": "客户",
        "api_name": "AccountObj",
    },
    "contact": {
        "description": "联系人",
        "api_name": "ContactObj",
    },
    "opportunity": {
        "description": "商机",
        "api_name": "OpportunityObj",
    },
    "contract": {
        "description": "合同",
        "api_name": "ContractObj",
    },
    "return_order": {
        "description": "退货申请",
        "api_name": "object_nko2c__c",
        "custom": True,
    },
    "return_order_detail": {
        "description": "退货申请明细",
        "api_name": "object_A3f18__c",
        "custom": True,
        "master_field": "field_4lTZ2__c",  # FK to return_order._id
    },
}


@register_connector("fenxiangxiaoke")
class FenxiangxiaokeConnector(BaseConnector):
    """纷享销客CRM连接器

    使用 corpAccessToken 认证，通过 /cgi/corpAccessToken/get/V2 获取。
    支持客户、联系人、商机、合同等实体的读写操作。
    """

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
        resp = self._client.request("POST", url, json=payload)
        resp.raise_for_status()
        result = resp.json()
        if result.get("errorCode") == 0:
            self._token = result.get("corpAccessToken")
            expire = result.get("expiresIn", 7200)
            self._token_expires_at = time.time() + expire - 300  # 提前5分钟刷新
        else:
            raise ConnectorPullError(f"纷享销客认证失败: {result}")

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
            url = f"{self.config['base_url']}/cgi/user/get"
            payload = {
                "corpAccessToken": self._token,
                "corpId": self.config.get("corp_id", ""),
            }
            self._request("POST", url, json=payload)
            latency = (time.time() - start) * 1000
            return HealthStatus(status="healthy", latency_ms=round(latency, 2))
        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthStatus(status="unhealthy", latency_ms=round(latency, 2), error=str(e))

    def list_entities(self) -> list[EntityInfo]:
        """列出支持的实体"""
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
        """拉取纷享销客实体数据

        Args:
            entity: 实体类型 (customer/contact/opportunity/contract)
            since: 增量同步起始时间
            filters: 额外过滤参数

        Returns:
            记录列表

        Raises:
            ConnectorPullError: 拉取失败时抛出
        """
        if entity not in FXIAOKE_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        self._ensure_token()
        entity_config = FXIAOKE_ENTITIES[entity]
        query_path = (
            FXIAOKE_CUSTOM_QUERY_PATH if entity_config.get("custom") else FXIAOKE_QUERY_PATH
        )
        url = f"{self.config['base_url']}{query_path}"

        all_records = []
        offset = 0

        try:
            while True:
                if offset // DEFAULT_PAGE_SIZE > MAX_PAGES:
                    logger.warning(f"Reached max page limit ({MAX_PAGES}) for entity={entity}")
                    break

                search_filters = []
                if filters and "filters" in filters:
                    search_filters.extend(filters["filters"])

                payload = {
                    "corpAccessToken": self._token,
                    "corpId": self.config.get("corp_id", ""),
                    "currentOpenUserId": self.config.get("open_user_id", ""),
                    "data": {
                        "dataObjectApiName": entity_config["api_name"],
                        "search_query_info": {
                            "limit": DEFAULT_PAGE_SIZE,
                            "offset": offset,
                            "filters": search_filters,
                            "orders": [],
                        },
                    },
                }

                result = self._request("POST", url, json=payload)

                data = result.get("data", {})
                if isinstance(result.get("errorCode"), int) and result["errorCode"] != 0:
                    error_msg = result.get("errorMessage", "未知错误")
                    raise ConnectorPullError(f"纷享销客 API 错误: {error_msg}")

                records = data.get("dataList", [])
                all_records.extend(records)

                total = data.get("totalNumber") or records[0].get("total_num", 0) if records else 0
                if not records or offset + len(records) >= total:
                    break

                offset += len(records)

            return all_records
        except ConnectorPullError:
            raise
        except Exception as e:
            logger.error(f"纷享销客拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        """推送数据到纷享销客"""
        if entity not in FXIAOKE_ENTITIES:
            raise ConnectorPushError(f"不支持的实体类型: {entity}")

        self._ensure_token()
        entity_config = FXIAOKE_ENTITIES[entity]
        url = f"{self.config['base_url']}{FXIAOKE_CREATE_PATH}"

        success_count = 0
        failure_count = 0
        failures = []

        for record in records:
            try:
                payload = {
                    "corpAccessToken": self._token,
                    "corpId": self.config.get("corp_id", ""),
                    "currentOpenUserId": self.config.get("open_user_id", ""),
                    "data": {
                        "dataObjectApiName": entity_config["api_name"],
                        "objectData": record,
                    },
                }

                result = self._request("POST", url, json=payload)

                if result.get("errorCode") == 0:
                    success_count += 1
                else:
                    failure_count += 1
                    failures.append(
                        {
                            "record": record,
                            "error": result.get("errorMessage", "未知错误"),
                        }
                    )
            except Exception as e:
                failure_count += 1
                failures.append(
                    {
                        "record": record,
                        "error": str(e),
                    }
                )

        return PushResult(
            success_count=success_count,
            failure_count=failure_count,
            failures=failures,
        )

    def pull_return_with_details(
        self,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        """拉取退货申请主表 + 关联明细行，返回合并后的记录列表。

        Each record has its original master fields plus a 'details' key
        containing the list of detail line records.
        """
        masters = self.pull("return_order", since=since, filters=filters)
        if not masters:
            return []

        self._ensure_token()
        detail_config = FXIAOKE_ENTITIES["return_order_detail"]
        detail_url = f"{self.config['base_url']}{FXIAOKE_CUSTOM_QUERY_PATH}"
        master_fk_field = detail_config["master_field"]

        for master in masters:
            master_id = master.get("_id", "")
            if not master_id:
                master["details"] = []
                continue

            try:
                detail_payload = {
                    "corpAccessToken": self._token,
                    "corpId": self.config.get("corp_id", ""),
                    "currentOpenUserId": self.config.get("open_user_id", ""),
                    "data": {
                        "dataObjectApiName": detail_config["api_name"],
                        "search_query_info": {
                            "limit": 100,
                            "offset": 0,
                            "filters": [
                                {
                                    "field_name": master_fk_field,
                                    "field_values": [master_id],
                                    "operator": "EQ",
                                }
                            ],
                            "orders": [{"fieldApiName": "order_by", "isAsc": True}],
                        },
                    },
                }
                result = self._request("POST", detail_url, json=detail_payload)
                if result.get("errorCode") == 0:
                    master["details"] = result.get("data", {}).get("dataList", [])
                else:
                    logger.warning(
                        "Failed to fetch return order details",
                        extra={
                            "master_id": master_id,
                            "error": result.get("errorMessage", ""),
                        },
                    )
                    master["details"] = []
            except Exception as e:
                logger.warning(
                    "Exception fetching return order details",
                    extra={"master_id": master_id, "error": str(e)},
                )
                master["details"] = []

        return masters

    def get_schema(self, entity: str) -> dict:
        """获取实体配置信息"""
        return FXIAOKE_ENTITIES.get(entity, {})

    def _prepare_request(self, method: str, url: str, headers: dict, kwargs: dict) -> None:
        headers["Content-Type"] = "application/json"
