# tests/test_connector_lingxing.py
import pytest
from unittest.mock import patch, MagicMock
import time
import hmac
import hashlib
from urllib.parse import urlencode

from src.connectors.lingxing import LingxingConnector, LINGXING_ENTITIES
from src.connectors.base import (
    HealthStatus, EntityInfo, PushResult,
    ConnectorPullError, connector_registry,
)


@pytest.fixture
def lingxing_config():
    return {
        "base_url": "https://openapi.lingxing.com",
        "app_id": "test_app_id",
        "app_secret": "test_app_secret_key_123",
    }


@pytest.fixture
def connector(lingxing_config):
    return LingxingConnector(config=lingxing_config)


# Test 1: Registry registration
def test_lingxing_registered():
    """领星连接器应已注册到全局注册表"""
    cls = connector_registry.get("lingxing")
    assert cls is LingxingConnector


# Test 2: List entities
def test_lingxing_list_entities(connector):
    """应返回支持的实体列表：product, order, inventory, shipment"""
    entities = connector.list_entities()
    assert len(entities) == 4
    names = [e.name for e in entities]
    assert "product" in names
    assert "order" in names
    assert "inventory" in names
    assert "shipment" in names
    # 验证实体信息完整
    for entity in entities:
        assert isinstance(entity, EntityInfo)
        assert entity.description != ""


# Test 3: Health check success
def test_lingxing_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"code": 0, "message": "success"}
        result = connector.health_check()
        assert result.status == "healthy"
        assert result.latency_ms is not None
        assert result.error is None


# Test 4: Health check failure
def test_lingxing_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"
        assert result.error is not None
        assert "Connection refused" in result.error


# Test 5: Pull success
def test_lingxing_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    mock_response = {
        "code": 0,
        "data": [
            {"product_id": "P001", "name": "商品A", "sku": "SKU001"},
            {"product_id": "P002", "name": "商品B", "sku": "SKU002"},
        ],
        "total": 2,
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="product")
        assert len(records) == 2
        assert records[0]["product_id"] == "P001"
        assert records[1]["sku"] == "SKU002"


# Test 6: Pull failure
def test_lingxing_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("API Error")
        with pytest.raises(ConnectorPullError) as exc_info:
            connector.pull(entity="product")
        assert "product" in str(exc_info.value)


# Test 7: Pull invalid entity
def test_lingxing_pull_invalid_entity_raises_error(connector):
    """拉取不支持的实体类型应抛出 ConnectorPullError"""
    with pytest.raises(ConnectorPullError) as exc_info:
        connector.pull(entity="invalid_entity")
    assert "不支持的实体类型" in str(exc_info.value)


# Test 8: Signature generation
def test_lingxing_signature_generation(connector):
    """签名生成应使用 HMAC-SHA256 算法"""
    params = {
        "app_id": "test_app_id",
        "timestamp": "1672531200",
        "page": "1",
        "size": "100",
    }
    
    # 手动计算期望的签名
    sorted_params = sorted(params.items())
    sign_string = urlencode(sorted_params)
    expected_signature = hmac.new(
        connector.config["app_secret"].encode("utf-8"),
        sign_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    # 调用连接器的签名方法
    actual_signature = connector._generate_signature(params)
    
    assert actual_signature == expected_signature
    # 签名应为 64 字符的十六进制字符串
    assert len(actual_signature) == 64
    assert all(c in "0123456789abcdef" for c in actual_signature)


# Test 9: Push returns all failures (read-only API)
def test_lingxing_push_returns_all_failures(connector):
    """领星不支持写入，push应返回所有记录失败"""
    records = [
        {"product_id": "P001", "name": "商品A"},
        {"product_id": "P002", "name": "商品B"},
        {"product_id": "P003", "name": "商品C"},
    ]
    result = connector.push(entity="product", records=records)
    assert result.success_count == 0
    assert result.failure_count == 3
    assert len(result.failures) == 3
    # 验证每个失败记录都有错误信息
    for failure in result.failures:
        assert "error" in failure
        assert "领星不支持此实体的写入" in failure["error"]


# Test 10: Pagination
def test_lingxing_pull_pagination(connector):
    """拉取数据应支持分页，获取所有页面的数据"""
    # 模拟分页响应：第一页有更多数据，第二页是最后一页
    page1_response = {
        "code": 0,
        "data": [
            {"product_id": "P001", "name": "商品A"},
            {"product_id": "P002", "name": "商品B"},
        ],
        "total": 3,
        "page": 1,
        "size": 2,
    }
    page2_response = {
        "code": 0,
        "data": [
            {"product_id": "P003", "name": "商品C"},
        ],
        "total": 3,
        "page": 2,
        "size": 2,
    }

    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = [page1_response, page2_response]
        records = connector.pull(entity="product")

        # 应该合并两页的数据
        assert len(records) == 3
        assert records[0]["product_id"] == "P001"
        assert records[1]["product_id"] == "P002"
        assert records[2]["product_id"] == "P003"

        # 验证分页请求
        assert mock_req.call_count == 2


# Test 11: Connect does nothing (signature-based auth)
def test_lingxing_connect_does_nothing(connector):
    """领星使用签名认证，connect 不需要获取 token"""
    # connect 应该不抛出异常，也不调用任何外部 API
    connector.connect()
    # 没有 token 属性 - 因为是签名认证
    assert not hasattr(connector, "_token") or connector._token is None


# Test 12: Pull all entities
def test_lingxing_pull_order_entity(connector):
    """拉取订单实体应成功"""
    mock_response = {
        "code": 0,
        "data": [
            {"order_id": "O001", "status": "shipped"},
        ],
        "total": 1,
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="order")
        assert len(records) == 1
        assert records[0]["order_id"] == "O001"


# Test 13: Pull inventory entity
def test_lingxing_pull_inventory_entity(connector):
    """拉取库存实体应成功"""
    mock_response = {
        "code": 0,
        "data": [
            {"sku": "SKU001", "quantity": 100},
        ],
        "total": 1,
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="inventory")
        assert len(records) == 1
        assert records[0]["quantity"] == 100


# Test 14: Pull shipment entity
def test_lingxing_pull_shipment_entity(connector):
    """拉取物流实体应成功"""
    mock_response = {
        "code": 0,
        "data": [
            {"shipment_id": "S001", "carrier": "顺丰"},
        ],
        "total": 1,
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="shipment")
        assert len(records) == 1
        assert records[0]["carrier"] == "顺丰"


# Test 15: Request includes signature in params
def test_lingxing_request_includes_signature(connector):
    """请求应包含签名参数"""
    with patch.object(connector._client, "request") as mock_client_req:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": []}
        mock_client_req.return_value = mock_response
        
        connector._request("GET", "https://openapi.lingxing.com/test", params={"foo": "bar"})
        
        # 验证请求被调用
        mock_client_req.assert_called_once()
        call_kwargs = mock_client_req.call_args[1]
        params = call_kwargs.get("params", {})
        
        # 应包含签名相关参数
        assert "sign" in params
        assert "app_id" in params
        assert "timestamp" in params
