# src/connectors/base.py
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import httpx


# --- 异常类 ---


class ConnectorError(Exception):
    """连接器通用异常"""

    pass


class ConnectorNotFoundError(ConnectorError):
    """连接器类型未注册"""

    pass


class ConnectorPullError(ConnectorError):
    """数据拉取失败"""

    pass


class ConnectorPushError(ConnectorError):
    """数据推送失败"""

    pass


# --- 数据类型 ---


@dataclass
class HealthStatus:
    status: str  # "healthy" | "unhealthy"
    latency_ms: float | None = None
    error: str | None = None


@dataclass
class EntityInfo:
    name: str
    description: str = ""
    supports_incremental: bool = True


@dataclass
class PushResult:
    success_count: int
    failure_count: int
    failures: list[dict] = field(default_factory=list)


# --- 抽象基类 ---


class BaseConnector(ABC):
    """连接器抽象基类，所有连接器必须实现此接口"""

    MAX_RETRIES = 3
    RETRY_BACKOFF = [1, 2, 4]

    def __init__(self, config: dict):
        self.config = config

    def _request(self, method: str, url: str, **kwargs) -> dict | list:
        headers = kwargs.pop("headers", {})
        self._prepare_request(method, url, headers, kwargs)
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = self._client.request(method, url, headers=headers, **kwargs)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", self.RETRY_BACKOFF[attempt]))
                    time.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_BACKOFF[attempt])
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise ConnectorError("Request failed without captured error")

    def _prepare_request(self, method: str, url: str, headers: dict, kwargs: dict) -> None:
        pass

    @abstractmethod
    def connect(self) -> None:
        """建立连接/认证"""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        ...

    @abstractmethod
    def health_check(self) -> HealthStatus:
        """健康检查"""
        ...

    @abstractmethod
    def list_entities(self) -> list[EntityInfo]:
        """列出支持的数据实体"""
        ...

    @abstractmethod
    def pull(
        self,
        entity: str,
        since: datetime | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        """从外部系统拉取数据"""
        ...

    @abstractmethod
    def push(self, entity: str, records: list[dict]) -> PushResult:
        """推送数据到外部系统"""
        ...

    @abstractmethod
    def get_schema(self, entity: str) -> dict:
        """获取实体字段结构"""
        ...


# --- 注册表 ---


class ConnectorRegistry:
    """连接器注册表，支持按类型查找"""

    def __init__(self):
        self._registry: dict[str, type[BaseConnector]] = {}

    def register(self, connector_type: str):
        """装饰器：注册连接器类"""

        def decorator(cls: type[BaseConnector]):
            self._registry[connector_type] = cls
            return cls

        return decorator

    def get(self, connector_type: str) -> type[BaseConnector]:
        """按类型查找连接器类"""
        if connector_type not in self._registry:
            raise ConnectorNotFoundError(
                f"连接器类型 '{connector_type}' 未注册。已注册: {list(self._registry.keys())}"
            )
        return self._registry[connector_type]

    def list_types(self) -> list[str]:
        """列出所有已注册的连接器类型"""
        return list(self._registry.keys())


# 全局注册表实例
connector_registry = ConnectorRegistry()
register_connector = connector_registry.register
