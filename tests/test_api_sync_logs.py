# tests/test_api_sync_logs.py
"""同步日志查询 API 测试"""
import pytest
from src.models.connector import Connector
from src.models.sync import SyncLog


@pytest.fixture
def connector_in_db(db_session):
    c = Connector(
        name="日志测试连接器",
        connector_type="kingdee_erp",
        base_url="https://erp.test.com",
        auth_config={"test": True},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


@pytest.fixture
def sample_logs(db_session, connector_in_db):
    """创建几条同步日志"""
    logs = []
    for i, status in enumerate(["success", "failure", "success"]):
        log = SyncLog(
            connector_id=connector_in_db.id,
            entity="order",
            direction="pull",
            status=status,
            total_records=10,
            success_count=10 if status == "success" else 0,
            failure_count=0 if status == "success" else 10,
        )
        db_session.add(log)
        logs.append(log)
    db_session.flush()
    return logs


class TestListSyncLogs:
    def test_list_empty(self, client, api_headers):
        resp = client.get("/api/v1/sync-logs", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_list_with_data(self, client, api_headers, sample_logs):
        resp = client.get("/api/v1/sync-logs", headers=api_headers)
        assert resp.json()["total_count"] == 3

    def test_filter_by_status(self, client, api_headers, sample_logs):
        resp = client.get("/api/v1/sync-logs?status=failure", headers=api_headers)
        data = resp.json()
        assert data["total_count"] == 1
        assert data["items"][0]["status"] == "failure"

    def test_filter_by_connector_id(self, client, api_headers, sample_logs, connector_in_db):
        resp = client.get(f"/api/v1/sync-logs?connector_id={connector_in_db.id}", headers=api_headers)
        assert resp.json()["total_count"] == 3

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/sync-logs")
        assert resp.status_code == 401
