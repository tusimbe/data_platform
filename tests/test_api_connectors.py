# tests/test_api_connectors.py
"""连接器管理 API 测试"""
import pytest


@pytest.fixture
def sample_connector_data():
    return {
        "name": "测试金蝶ERP",
        "connector_type": "kingdee_erp",
        "base_url": "https://erp.test.com",
        "auth_config": {"acct_id": "test", "username": "admin", "password": "secret"},
        "description": "测试环境",
    }


class TestCreateConnector:
    def test_create_success(self, client, api_headers, sample_connector_data):
        resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "测试金蝶ERP"
        assert data["connector_type"] == "kingdee_erp"
        assert data["enabled"] is True
        assert data["has_auth_config"] is True
        assert "auth_config" not in data  # 凭证不暴露

    def test_create_invalid_type(self, client, api_headers):
        resp = client.post("/api/v1/connectors", json={
            "name": "bad", "connector_type": "invalid", "base_url": "http://x",
        }, headers=api_headers)
        assert resp.status_code == 400

    def test_create_duplicate_name(self, client, api_headers, sample_connector_data):
        client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        assert resp.status_code == 409

    def test_create_requires_auth(self, client, sample_connector_data):
        resp = client.post("/api/v1/connectors", json=sample_connector_data)
        assert resp.status_code == 401


class TestListConnectors:
    def test_list_empty(self, client, api_headers):
        resp = client.get("/api/v1/connectors", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total_count"] == 0

    def test_list_with_pagination(self, client, api_headers, sample_connector_data):
        # 创建 2 个连接器
        client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        data2 = {**sample_connector_data, "name": "第二个"}
        client.post("/api/v1/connectors", json=data2, headers=api_headers)
        resp = client.get("/api/v1/connectors?page=1&page_size=1", headers=api_headers)
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total_count"] == 2


class TestGetConnector:
    def test_get_success(self, client, api_headers, sample_connector_data):
        create_resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        cid = create_resp.json()["id"]
        resp = client.get(f"/api/v1/connectors/{cid}", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "测试金蝶ERP"

    def test_get_not_found(self, client, api_headers):
        resp = client.get("/api/v1/connectors/999", headers=api_headers)
        assert resp.status_code == 404


class TestUpdateConnector:
    def test_update_success(self, client, api_headers, sample_connector_data):
        create_resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        cid = create_resp.json()["id"]
        resp = client.put(f"/api/v1/connectors/{cid}", json={"name": "新名称"}, headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "新名称"


class TestDeleteConnector:
    def test_soft_delete(self, client, api_headers, sample_connector_data):
        create_resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        cid = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/connectors/{cid}", headers=api_headers)
        assert resp.status_code == 204
        # 验证已禁用
        get_resp = client.get(f"/api/v1/connectors/{cid}", headers=api_headers)
        assert get_resp.json()["enabled"] is False

    def test_delete_cascades_sync_tasks(self, client, api_headers, sample_connector_data, db_session):
        """软删除应级联禁用关联的同步任务"""
        create_resp = client.post("/api/v1/connectors", json=sample_connector_data, headers=api_headers)
        cid = create_resp.json()["id"]
        # 通过 DB 直接添加同步任务（因为同步任务 API 还没实现）
        from src.models.sync import SyncTask
        task = SyncTask(connector_id=cid, entity="order", direction="pull", enabled=True)
        db_session.add(task)
        db_session.flush()
        task_id = task.id

        client.delete(f"/api/v1/connectors/{cid}", headers=api_headers)

        refreshed_task = db_session.query(SyncTask).filter_by(id=task_id).first()
        assert refreshed_task.enabled is False
