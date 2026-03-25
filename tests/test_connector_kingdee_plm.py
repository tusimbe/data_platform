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
