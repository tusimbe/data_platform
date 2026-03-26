# tests/test_connector_kingdee.py
import pytest
from unittest.mock import patch

from src.connectors.kingdee_erp import KingdeeERPConnector
from src.connectors.base import ConnectorPullError, connector_registry


@pytest.fixture
def kingdee_config():
    return {
        "base_url": "https://api.kingdee.com",
        "app_id": "test_app_id",
        "app_secret": "test_app_secret",
        "acct_id": "test_acct_id",
    }


@pytest.fixture
def connector(kingdee_config):
    return KingdeeERPConnector(config=kingdee_config)


def test_kingdee_registered():
    """金蝶ERP连接器应已注册到全局注册表"""
    cls = connector_registry.get("kingdee_erp")
    assert cls is KingdeeERPConnector


def test_kingdee_list_entities(connector):
    """应返回支持的实体列表"""
    entities = connector.list_entities()
    assert len(entities) > 0
    names = [e.name for e in entities]
    assert "sales_order" in names
    assert "purchase_order" in names


def test_kingdee_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"Result": {"ResponseStatus": {"IsSuccess": True}}}
        result = connector.health_check()
        assert result.status == "healthy"
        assert result.latency_ms is not None


def test_kingdee_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"
        assert "Connection refused" in result.error


def test_kingdee_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    mock_response = [
        {"FBillNo": "SO-001", "FDate": "2026-01-01", "FAmount": 1000},
        {"FBillNo": "SO-002", "FDate": "2026-01-02", "FAmount": 2000},
    ]
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="sales_order")
        assert len(records) == 2
        assert records[0]["FBillNo"] == "SO-001"


def test_kingdee_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("API Error 500")
        with pytest.raises(ConnectorPullError):
            connector.pull(entity="sales_order")


def test_kingdee_connect_gets_token(connector):
    """connect() 应获取会话令牌"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {
            "KDToken": "mock-token-123",
            "IsSuccessByAPI": True,
        }
        connector.connect()
        assert connector._token == "mock-token-123"


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


def test_kingdee_pull_max_pages_cap(connector):
    from src.connectors.kingdee_erp import MAX_PAGES

    full_page = [{"FBillNo": f"SO-{i}"} for i in range(2000)]

    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return full_page

    with patch.object(connector, "_request", side_effect=mock_request):
        records = connector.pull(entity="sales_order")

    assert call_count == MAX_PAGES
    assert len(records) == MAX_PAGES * 2000


def test_kingdee_pull_multi_page(connector):
    page1 = [{"FBillNo": f"SO-{i}"} for i in range(2000)]
    page2 = [{"FBillNo": f"SO-{i}"} for i in range(2000, 2500)]

    pages = [page1, page2]
    call_idx = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_idx
        result = pages[call_idx]
        call_idx += 1
        return result

    with patch.object(connector, "_request", side_effect=mock_request):
        records = connector.pull(entity="sales_order")

    assert call_idx == 2
    assert len(records) == 2500
