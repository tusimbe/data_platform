# tests/test_api_data.py
"""统一数据 + 原始数据查询 API 测试"""
import pytest
from src.models.unified import UnifiedCustomer, UnifiedOrder
from src.models.connector import Connector
from src.models.raw_data import RawData


@pytest.fixture
def sample_customers(db_session):
    """创建测试客户数据"""
    customers = []
    for i in range(3):
        c = UnifiedCustomer(
            name=f"客户{i}",
            source_system="fenxiangxiaoke",
            external_id=f"ext_{i}",
            status="active" if i < 2 else "inactive",
        )
        db_session.add(c)
        customers.append(c)
    db_session.flush()
    return customers


@pytest.fixture
def raw_data_in_db(db_session):
    """创建原始数据"""
    c = Connector(
        name="原始数据测试连接器",
        connector_type="kingdee_erp",
        base_url="https://erp.test.com",
        auth_config={},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    for i in range(2):
        rd = RawData(
            connector_id=c.id,
            entity="sales_order",
            external_id=f"SO{i}",
            data={"FBillNo": f"SO{i}", "amount": 100 * i},
        )
        db_session.add(rd)
    db_session.flush()
    return c


class TestListUnifiedData:
    def test_list_customers(self, client, api_headers, sample_customers):
        resp = client.get("/api/v1/data/customers", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3

    def test_list_with_filter(self, client, api_headers, sample_customers):
        resp = client.get("/api/v1/data/customers?status=active", headers=api_headers)
        data = resp.json()
        assert data["total_count"] == 2

    def test_list_invalid_entity(self, client, api_headers):
        resp = client.get("/api/v1/data/unknown", headers=api_headers)
        assert resp.status_code == 404

    def test_list_invalid_filter_column(self, client, api_headers, sample_customers):
        resp = client.get("/api/v1/data/customers?nonexistent=value", headers=api_headers)
        assert resp.status_code == 400

    def test_list_with_sorting(self, client, api_headers, sample_customers):
        resp = client.get("/api/v1/data/customers?sort_by=name&sort_order=asc", headers=api_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        names = [item["name"] for item in items]
        assert names == sorted(names)

    def test_list_with_pagination(self, client, api_headers, sample_customers):
        resp = client.get("/api/v1/data/customers?page=1&page_size=2", headers=api_headers)
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total_count"] == 3


class TestGetUnifiedRecord:
    def test_get_success(self, client, api_headers, sample_customers):
        cid = sample_customers[0].id
        resp = client.get(f"/api/v1/data/customers/{cid}", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "客户0"

    def test_get_not_found(self, client, api_headers):
        resp = client.get("/api/v1/data/customers/999", headers=api_headers)
        assert resp.status_code == 404


class TestListRawData:
    def test_list_raw(self, client, api_headers, raw_data_in_db):
        resp = client.get("/api/v1/raw/kingdee_erp/sales_order", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert "data" in data["items"][0]

    def test_raw_no_connector(self, client, api_headers):
        resp = client.get("/api/v1/raw/nonexistent/order", headers=api_headers)
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/data/customers")
        assert resp.status_code == 401
