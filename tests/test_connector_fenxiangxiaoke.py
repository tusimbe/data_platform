# tests/test_connector_fenxiangxiaoke.py
import pytest
from unittest.mock import patch, MagicMock
import time

from src.connectors.base import (
    HealthStatus,
    EntityInfo,
    PushResult,
    ConnectorPullError,
    ConnectorPushError,
    connector_registry,
)


@pytest.fixture
def fxiaoke_config():
    return {
        "base_url": "https://open.fxiaoke.com",
        "app_id": "test_app_id",
        "app_secret": "test_app_secret",
        "permanent_code": "test_permanent_code",
    }


@pytest.fixture
def connector(fxiaoke_config):
    from src.connectors.fenxiangxiaoke import FenxiangxiaokeConnector

    return FenxiangxiaokeConnector(config=fxiaoke_config)


def test_fenxiangxiaoke_registered():
    """纷享销客连接器应已注册到全局注册表"""
    from src.connectors.fenxiangxiaoke import FenxiangxiaokeConnector

    cls = connector_registry.get("fenxiangxiaoke")
    assert cls is FenxiangxiaokeConnector


def test_fenxiangxiaoke_list_entities(connector):
    """应返回支持的实体列表"""
    entities = connector.list_entities()
    assert len(entities) == 4
    names = [e.name for e in entities]
    assert "customer" in names
    assert "contact" in names
    assert "opportunity" in names
    assert "contract" in names


def test_fenxiangxiaoke_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"errorCode": 0}
        result = connector.health_check()
        assert result.status == "healthy"
        assert result.latency_ms is not None


def test_fenxiangxiaoke_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"
        assert result.error is not None
        assert "Connection refused" in result.error


def test_fenxiangxiaoke_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200

    mock_response = {
        "errorCode": 0,
        "data": {
            "dataList": [
                {"_id": "cust_001", "name": "客户A", "industry": "IT", "total_num": 2},
                {"_id": "cust_002", "name": "客户B", "industry": "金融", "total_num": 2},
            ],
        },
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="customer")
        assert len(records) == 2
        assert records[0]["_id"] == "cust_001"
        assert records[1]["name"] == "客户B"


def test_fenxiangxiaoke_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200

    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"errorCode": 500, "errorMessage": "Internal Error"}
        with pytest.raises(ConnectorPullError) as exc_info:
            connector.pull(entity="customer")
        assert "Internal Error" in str(exc_info.value)


def test_fenxiangxiaoke_pull_invalid_entity_raises_error(connector):
    """拉取不支持的实体类型应抛出 ConnectorPullError"""
    with pytest.raises(ConnectorPullError) as exc_info:
        connector.pull(entity="invalid_entity")
    assert "不支持的实体类型" in str(exc_info.value)


def test_fenxiangxiaoke_connect_gets_token(connector):
    """connect() 应获取 corpAccessToken"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "errorCode": 0,
        "corpAccessToken": "corp-token-test-123",
        "expiresIn": 7200,
    }
    mock_resp.raise_for_status = MagicMock()
    with patch.object(connector._client, "request", return_value=mock_resp):
        connector.connect()
        assert connector._token == "corp-token-test-123"


def test_fenxiangxiaoke_push_success(connector):
    """推送数据成功应返回正确的 PushResult"""
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200

    records = [
        {"name": "新客户A", "industry": "IT"},
        {"name": "新客户B", "industry": "金融"},
    ]

    with patch.object(connector, "_request") as mock_req:
        # 两次调用都成功
        mock_req.return_value = {"errorCode": 0, "data": {"_id": "new_id"}}
        result = connector.push(entity="customer", records=records)

        assert result.success_count == 2
        assert result.failure_count == 0
        assert len(result.failures) == 0


def test_fenxiangxiaoke_push_partial_failure(connector):
    """推送部分失败应返回正确的成功和失败计数"""
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200

    records = [
        {"name": "新客户A", "industry": "IT"},
        {"name": "新客户B", "industry": "金融"},
        {"name": "新客户C", "industry": "制造"},
    ]

    with patch.object(connector, "_request") as mock_req:
        # 第一个成功，第二个失败，第三个成功
        mock_req.side_effect = [
            {"errorCode": 0, "data": {"_id": "new_id_1"}},
            {"errorCode": 400, "errorMessage": "Invalid data"},
            {"errorCode": 0, "data": {"_id": "new_id_3"}},
        ]
        result = connector.push(entity="customer", records=records)

        assert result.success_count == 2
        assert result.failure_count == 1
        assert len(result.failures) == 1
        assert "Invalid data" in result.failures[0]["error"]


def test_fenxiangxiaoke_pull_pagination(connector):
    """拉取数据应支持分页，获取所有页面的数据"""
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200

    # 模拟分页响应：第一页有更多数据，第二页是最后一页
    page1_response = {
        "errorCode": 0,
        "data": {
            "dataList": [
                {"_id": "cust_001", "name": "客户A", "total_num": 3},
                {"_id": "cust_002", "name": "客户B", "total_num": 3},
            ],
        },
    }
    page2_response = {
        "errorCode": 0,
        "data": {
            "dataList": [
                {"_id": "cust_003", "name": "客户C", "total_num": 3},
            ],
        },
    }

    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = [page1_response, page2_response]
        records = connector.pull(entity="customer")

        assert len(records) == 3
        assert records[0]["_id"] == "cust_001"
        assert records[1]["_id"] == "cust_002"
        assert records[2]["_id"] == "cust_003"

        assert mock_req.call_count == 2
        second_call_kwargs = mock_req.call_args_list[1][1]
        if "json" in second_call_kwargs:
            assert second_call_kwargs["json"]["data"]["search_query_info"]["offset"] == 2


def test_fenxiangxiaoke_disconnect(connector):
    """disconnect() 应清除 token"""
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200

    connector.disconnect()

    assert connector._token is None
    assert connector._token_expires_at == 0


def test_fenxiangxiaoke_get_schema(connector):
    """get_schema() 应返回实体配置信息"""
    schema = connector.get_schema("customer")
    assert "description" in schema
    assert "api_name" in schema

    # 不存在的实体应返回空字典
    empty_schema = connector.get_schema("nonexistent")
    assert empty_schema == {}
