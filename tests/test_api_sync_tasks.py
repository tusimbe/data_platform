# tests/test_api_sync_tasks.py
"""同步任务管理 API 测试"""
import pytest
from src.models.connector import Connector


@pytest.fixture
def connector_in_db(db_session):
    """在 DB 中创建一个连接器供同步任务使用"""
    c = Connector(
        name="测试连接器",
        connector_type="kingdee_erp",
        base_url="https://erp.test.com",
        auth_config={"test": True},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


@pytest.fixture
def sample_task_data(connector_in_db):
    return {
        "connector_id": connector_in_db.id,
        "entity": "order",
        "direction": "pull",
        "cron_expression": "0 */2 * * *",
        "enabled": True,
    }


class TestCreateSyncTask:
    def test_create_success(self, client, api_headers, sample_task_data):
        resp = client.post("/api/v1/sync-tasks", json=sample_task_data, headers=api_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["entity"] == "order"
        assert data["direction"] == "pull"
        assert data["enabled"] is True
        assert "next_run_at" in data

    def test_create_without_cron(self, client, api_headers, connector_in_db):
        resp = client.post("/api/v1/sync-tasks", json={
            "connector_id": connector_in_db.id,
            "entity": "order",
            "direction": "pull",
        }, headers=api_headers)
        assert resp.status_code == 201
        assert resp.json()["cron_expression"] is None

    def test_create_invalid_connector(self, client, api_headers):
        resp = client.post("/api/v1/sync-tasks", json={
            "connector_id": 999,
            "entity": "order",
            "direction": "pull",
        }, headers=api_headers)
        assert resp.status_code == 400

    def test_create_invalid_direction(self, client, api_headers, connector_in_db):
        resp = client.post("/api/v1/sync-tasks", json={
            "connector_id": connector_in_db.id,
            "entity": "order",
            "direction": "invalid",
        }, headers=api_headers)
        assert resp.status_code == 422

    def test_create_requires_auth(self, client, sample_task_data):
        resp = client.post("/api/v1/sync-tasks", json=sample_task_data)
        assert resp.status_code == 401


class TestListSyncTasks:
    def test_list_empty(self, client, api_headers):
        resp = client.get("/api/v1/sync-tasks", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_list_with_data(self, client, api_headers, sample_task_data):
        client.post("/api/v1/sync-tasks", json=sample_task_data, headers=api_headers)
        resp = client.get("/api/v1/sync-tasks", headers=api_headers)
        assert resp.json()["total_count"] == 1


class TestUpdateSyncTask:
    def test_update_success(self, client, api_headers, sample_task_data):
        create_resp = client.post("/api/v1/sync-tasks", json=sample_task_data, headers=api_headers)
        tid = create_resp.json()["id"]
        resp = client.put(f"/api/v1/sync-tasks/{tid}", json={"enabled": False}, headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


class TestDeleteSyncTask:
    def test_delete_success(self, client, api_headers, sample_task_data):
        create_resp = client.post("/api/v1/sync-tasks", json=sample_task_data, headers=api_headers)
        tid = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/sync-tasks/{tid}", headers=api_headers)
        assert resp.status_code == 204
        # 验证已删除
        get_resp = client.get(f"/api/v1/sync-tasks/{tid}", headers=api_headers)
        assert get_resp.status_code == 404
