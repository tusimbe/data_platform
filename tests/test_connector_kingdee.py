# tests/test_connector_kingdee.py
import pytest
from unittest.mock import patch

from src.connectors.kingdee_erp import KingdeeERPConnector, KINGDEE_ENTITIES
from src.connectors.base import ConnectorPullError, ConnectorError, connector_registry


@pytest.fixture
def kingdee_config():
    return {
        "base_url": "https://api.kingdee.com",
        "acct_id": "test_acct_id",
        "username": "test_user",
        "password": "test_pass",
    }


@pytest.fixture
def connector(kingdee_config):
    return KingdeeERPConnector(config=kingdee_config)


def test_kingdee_registered():
    cls = connector_registry.get("kingdee_erp")
    assert cls is KingdeeERPConnector


def test_kingdee_list_entities(connector):
    entities = connector.list_entities()
    assert len(entities) > 0
    names = [e.name for e in entities]
    assert "sales_order" in names
    assert "purchase_order" in names


def test_kingdee_health_check_success(connector):
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"Result": {"ResponseStatus": {"IsSuccess": True}}}
        result = connector.health_check()
        assert result.status == "healthy"
        assert result.latency_ms is not None


def test_kingdee_health_check_failure(connector):
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"
        assert "Connection refused" in result.error


def test_kingdee_connect_success(connector):
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {
            "IsSuccessByAPI": True,
            "LoginResultType": 1,
            "KDSVCSessionId": "test-session-id",
        }
        connector.connect()
        assert connector._authenticated is True


def test_kingdee_connect_failure(connector):
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {
            "IsSuccessByAPI": False,
            "LoginResultType": 0,
            "Message": "Invalid credentials",
        }
        with pytest.raises(ConnectorError, match="Auth failed"):
            connector.connect()


def test_kingdee_pull_success(connector):
    field_keys = KINGDEE_ENTITIES["sales_order"]["field_keys"]
    mock_rows = [
        [
            "SO-001",
            "2026-01-01",
            "标准销售订单",
            "客户A",
            "销售员1",
            "组织1",
            "C",
            "2026-01-02",
            "销售部",
        ],
        [
            "SO-002",
            "2026-01-02",
            "标准销售订单",
            "客户B",
            "销售员2",
            "组织1",
            "C",
            "2026-01-03",
            "销售部",
        ],
    ]
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_rows
        records = connector.pull(entity="sales_order")
        assert len(records) == 2
        assert records[0]["FBillNo"] == "SO-001"
        assert records[0]["FCustId.FName"] == "客户A"
        assert records[1]["FBillNo"] == "SO-002"

        call_payload = mock_req.call_args[1]["json"]
        assert "data" in call_payload
        assert call_payload["data"]["FormId"] == "SAL_SaleOrder"
        assert call_payload["data"]["FieldKeys"] == ",".join(field_keys)


def test_kingdee_pull_failure(connector):
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("API Error 500")
        with pytest.raises(ConnectorPullError):
            connector.pull(entity="sales_order")


def test_kingdee_pull_unsupported_entity(connector):
    with pytest.raises(ConnectorPullError, match="不支持的实体类型"):
        connector.pull(entity="nonexistent")


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

    field_keys = KINGDEE_ENTITIES["sales_order"]["field_keys"]
    full_page = [["SO-001"] + [""] * (len(field_keys) - 1)] * 2000

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
    field_keys = KINGDEE_ENTITIES["sales_order"]["field_keys"]
    page1 = [[f"SO-{i}"] + [""] * (len(field_keys) - 1) for i in range(2000)]
    page2 = [[f"SO-{i}"] + [""] * (len(field_keys) - 1) for i in range(2000, 2500)]

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
    assert records[0]["FBillNo"] == "SO-0"
    assert records[2499]["FBillNo"] == "SO-2499"


def test_rows_to_dicts():
    rows = [
        [1, "A", "B"],
        [2, "C", "D"],
    ]
    keys = ["id", "name", "desc"]
    result = KingdeeERPConnector._rows_to_dicts(rows, keys)
    assert len(result) == 2
    assert result[0] == {"id": 1, "name": "A", "desc": "B"}
    assert result[1] == {"id": 2, "name": "C", "desc": "D"}


def test_rows_to_dicts_skips_non_list():
    rows = [
        [1, "A"],
        {"error": "something"},
        [2, "B"],
    ]
    keys = ["id", "name"]
    result = KingdeeERPConnector._rows_to_dicts(rows, keys)
    assert len(result) == 2


def test_kingdee_push_wraps_data(connector):
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"Result": {"ResponseStatus": {"IsSuccess": True}}}
        connector.push("sales_order", [{"FBillNo": "SO-001"}])

        call_payload = mock_req.call_args[1]["json"]
        assert "data" in call_payload
        assert call_payload["data"]["FormId"] == "SAL_SaleOrder"
