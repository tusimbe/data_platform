# tests/test_connector_kingdee_plm.py
import pytest
from unittest.mock import patch

from src.connectors.kingdee_plm import KingdeePLMConnector
from src.connectors.base import ConnectorPullError, connector_registry


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
    assert "change_order" in names


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


def test_kingdee_plm_pull_invalid_entity(connector):
    """拉取不支持的实体类型应抛出 ConnectorPullError"""
    with pytest.raises(ConnectorPullError) as exc_info:
        connector.pull(entity="invalid_entity")
    assert "不支持的实体类型" in str(exc_info.value)


def test_kingdee_plm_push_success(connector):
    """推送多条记录成功应返回正确计数"""
    records = [
        {"FNumber": "P-001", "FName": "产品A"},
        {"FNumber": "P-002", "FName": "产品B"},
        {"FNumber": "P-003", "FName": "产品C"},
    ]
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"IsSuccess": True}
        result = connector.push(entity="product", records=records)
        assert result.success_count == 3
        assert result.failure_count == 0
        assert result.failures == []


def test_kingdee_plm_push_partial_failure(connector):
    """推送部分失败应返回正确的成功/失败计数和失败详情"""
    records = [
        {"FNumber": "P-001", "FName": "产品A"},
        {"FNumber": "P-002", "FName": "产品B"},
        {"FNumber": "P-003", "FName": "产品C"},
    ]
    with patch.object(connector, "_request") as mock_req:
        # 第一条成功，第二条失败，第三条成功
        mock_req.side_effect = [
            {"IsSuccess": True},
            Exception("Duplicate key error"),
            {"IsSuccess": True},
        ]
        result = connector.push(entity="product", records=records)
        assert result.success_count == 2
        assert result.failure_count == 1
        assert len(result.failures) == 1
        assert result.failures[0]["record"] == "P-002"
        assert "Duplicate key error" in result.failures[0]["error"]


def test_sanitize_filter_value_accepts_safe_value(connector):
    assert connector._sanitize_filter_value("2026-01-01 00:00:00") == "2026-01-01 00:00:00"
    assert connector._sanitize_filter_value("SAL_SaleOrder") == "SAL_SaleOrder"
    assert connector._sanitize_filter_value("test/path:value") == "test/path:value"


def test_sanitize_filter_value_rejects_sql_injection(connector):
    with pytest.raises(ConnectorPullError, match="Invalid filter value"):
        connector._sanitize_filter_value("'; DROP TABLE --")


def test_sanitize_filter_value_rejects_single_quotes(connector):
    with pytest.raises(ConnectorPullError, match="Invalid filter value"):
        connector._sanitize_filter_value("test'value")


def test_sanitize_filter_value_rejects_parentheses(connector):
    with pytest.raises(ConnectorPullError, match="Invalid filter value"):
        connector._sanitize_filter_value("test()")
