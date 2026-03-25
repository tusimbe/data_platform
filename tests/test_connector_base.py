# tests/test_connector_base.py
import pytest
from datetime import datetime

from src.connectors.base import (
    BaseConnector, ConnectorRegistry, register_connector,
    HealthStatus, EntityInfo, PushResult,
    ConnectorNotFoundError, ConnectorPullError, ConnectorError,
)


def test_base_connector_is_abstract():
    """BaseConnector 不能直接实例化"""
    with pytest.raises(TypeError):
        BaseConnector(config={})


def test_register_and_lookup_connector():
    """注册器应能注册和查找连接器"""
    registry = ConnectorRegistry()

    @registry.register("test_system")
    class TestConnector(BaseConnector):
        def connect(self): pass
        def disconnect(self): pass
        def health_check(self): return HealthStatus(status="healthy", latency_ms=10)
        def list_entities(self): return []
        def pull(self, entity, since=None, filters=None): return []
        def push(self, entity, records): return PushResult(success_count=0, failure_count=0)
        def get_schema(self, entity): return {}

    cls = registry.get("test_system")
    assert cls is TestConnector


def test_lookup_unknown_connector():
    """查找未注册的连接器应抛出 ConnectorNotFoundError"""
    registry = ConnectorRegistry()
    with pytest.raises(ConnectorNotFoundError):
        registry.get("nonexistent")


def test_health_status_dataclass():
    """HealthStatus 数据类应正常工作"""
    h = HealthStatus(status="healthy", latency_ms=42)
    assert h.status == "healthy"
    assert h.latency_ms == 42

    h2 = HealthStatus(status="unhealthy", error="connection refused")
    assert h2.error == "connection refused"


def test_push_result_dataclass():
    """PushResult 数据类应正常工作"""
    r = PushResult(success_count=8, failure_count=2, failures=[{"id": "1", "error": "invalid"}])
    assert r.success_count == 8
    assert len(r.failures) == 1
