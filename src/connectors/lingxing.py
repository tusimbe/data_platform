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

DEFAULT_PAGE_SIZE = 100

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
        self._token = None  # 领星不使用 token，但保留属性以兼容测试

    def connect(self) -> None:
        """领星使用 HMAC 签名，无需预先获取 token"""
        pass

    def disconnect(self) -> None:
        self._client.close()

    def _generate_signature(self, params: dict) -> str:
        """生成 HMAC-SHA256 签名
        
        Args:
            params: 请求参数字典
            
        Returns:
            签名字符串
        """
        sorted_params = sorted(params.items())
        sign_string = urlencode(sorted_params)
        
        signature = hmac.new(
            self.config["app_secret"].encode("utf-8"),
            sign_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        return signature

    def health_check(self) -> HealthStatus:
        """调用轻量 API 验证连接"""
        start = time.time()
        try:
            # 使用产品列表 API 进行健康检查，限制返回 1 条
            url = f"{self.config['base_url']}{LINGXING_ENTITIES['product']['path']}"
            self._request("GET", url, params={"page": 1, "size": 1})
            latency = (time.time() - start) * 1000
            return HealthStatus(status="healthy", latency_ms=round(latency, 2))
        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthStatus(
                status="unhealthy", latency_ms=round(latency, 2), error=str(e)
            )

    def list_entities(self) -> list[EntityInfo]:
        """列出支持的实体类型"""
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
        """拉取领星实体数据
        
        Args:
            entity: 实体类型 (product/order/inventory/shipment)
            since: 增量同步起始时间
            filters: 额外过滤参数
            
        Returns:
            记录列表
            
        Raises:
            ConnectorPullError: 拉取失败时抛出
        """
        if entity not in LINGXING_ENTITIES:
            raise ConnectorPullError(f"不支持的实体类型: {entity}")

        entity_config = LINGXING_ENTITIES[entity]
        url = f"{self.config['base_url']}{entity_config['path']}"

        all_records = []
        page = 1

        try:
            while True:
                params = {"page": page, "size": DEFAULT_PAGE_SIZE}
                if filters:
                    params.update(filters)

                result = self._request("GET", url, params=params)
                
                if result.get("code") != 0:
                    raise ConnectorPullError(f"领星 API 错误: {result.get('message')}")

                data = result.get("data", [])
                all_records.extend(data)

                # 检查是否还有更多数据
                total = result.get("total", len(data))
                if len(all_records) >= total or len(data) == 0:
                    break
                    
                page += 1

            return all_records
        except ConnectorPullError:
            raise
        except Exception as e:
            logger.error(f"领星拉取失败: entity={entity}, error={e}")
            raise ConnectorPullError(f"拉取 {entity} 失败: {e}") from e

    def push(self, entity: str, records: list[dict]) -> PushResult:
        """领星不支持写入，返回失败结果
        
        Args:
            entity: 实体类型
            records: 要推送的记录列表
            
        Returns:
            PushResult，所有记录标记为失败
        """
        return PushResult(
            success_count=0,
            failure_count=len(records),
            failures=[
                {"record": r, "error": "领星不支持此实体的写入"} for r in records
            ]
        )

    def get_schema(self, entity: str) -> dict:
        """获取实体字段结构"""
        return LINGXING_ENTITIES.get(entity, {})

    def _request(
        self, method: str, url: str, params: dict | None = None, **kwargs
    ) -> dict:
        """带签名的 HTTP 请求
        
        Args:
            method: HTTP 方法
            url: 请求 URL
            params: 请求参数
            **kwargs: 其他 httpx 参数
            
        Returns:
            响应 JSON
        """
        params = params or {}
        
        # 添加签名相关参数
        params["app_id"] = self.config["app_id"]
        params["timestamp"] = str(int(time.time()))
        
        # 生成签名
        params["sign"] = self._generate_signature(params)

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._client.request(method, url, params=params, **kwargs)

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
