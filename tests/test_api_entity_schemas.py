import pytest


@pytest.fixture
def sample_schema_data():
    return {
        "connector_type": "fenxiangxiaoke",
        "entity": "customer",
        "schema_data": {
            "fields": [
                {"name": "account_name", "type": "string", "label": "客户名称"},
                {"name": "owner", "type": "string", "label": "负责人"},
                {"name": "create_time", "type": "datetime", "label": "创建时间"},
            ]
        },
    }


class TestCreateEntitySchema:
    def test_create_success(self, client, api_headers, sample_schema_data):
        resp = client.post("/api/v1/entity-schemas", json=sample_schema_data, headers=api_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["connector_type"] == "fenxiangxiaoke"
        assert data["entity"] == "customer"
        assert len(data["schema_data"]["fields"]) == 3
        assert "id" in data
        assert "created_at" in data

    def test_create_upserts_existing(self, client, api_headers, sample_schema_data):
        resp1 = client.post("/api/v1/entity-schemas", json=sample_schema_data, headers=api_headers)
        first_id = resp1.json()["id"]

        updated = {
            **sample_schema_data,
            "schema_data": {"fields": [{"name": "new_field", "type": "int"}]},
        }
        resp2 = client.post("/api/v1/entity-schemas", json=updated, headers=api_headers)
        assert resp2.status_code == 201
        assert resp2.json()["id"] == first_id
        assert resp2.json()["schema_data"]["fields"][0]["name"] == "new_field"

    def test_create_requires_auth(self, client, sample_schema_data):
        resp = client.post("/api/v1/entity-schemas", json=sample_schema_data)
        assert resp.status_code == 401

    def test_create_missing_required(self, client, api_headers):
        resp = client.post(
            "/api/v1/entity-schemas", json={"connector_type": "x"}, headers=api_headers
        )
        assert resp.status_code == 422


class TestListEntitySchemas:
    def test_list_empty(self, client, api_headers):
        resp = client.get("/api/v1/entity-schemas", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total_count"] == 0

    def test_list_with_data(self, client, api_headers, sample_schema_data):
        client.post("/api/v1/entity-schemas", json=sample_schema_data, headers=api_headers)
        resp = client.get("/api/v1/entity-schemas", headers=api_headers)
        data = resp.json()
        assert data["total_count"] == 1

    def test_list_filter_by_connector_type(self, client, api_headers, sample_schema_data):
        client.post("/api/v1/entity-schemas", json=sample_schema_data, headers=api_headers)
        other = {**sample_schema_data, "connector_type": "kingdee_erp", "entity": "material"}
        client.post("/api/v1/entity-schemas", json=other, headers=api_headers)

        resp = client.get(
            "/api/v1/entity-schemas?connector_type=fenxiangxiaoke", headers=api_headers
        )
        data = resp.json()
        assert data["total_count"] == 1
        assert data["items"][0]["connector_type"] == "fenxiangxiaoke"

    def test_list_filter_by_entity(self, client, api_headers, sample_schema_data):
        client.post("/api/v1/entity-schemas", json=sample_schema_data, headers=api_headers)
        other = {**sample_schema_data, "entity": "order", "schema_data": {"fields": []}}
        client.post("/api/v1/entity-schemas", json=other, headers=api_headers)

        resp = client.get("/api/v1/entity-schemas?entity=customer", headers=api_headers)
        data = resp.json()
        assert data["total_count"] == 1

    def test_list_pagination(self, client, api_headers):
        for i in range(3):
            data = {
                "connector_type": f"type_{i}",
                "entity": "customer",
                "schema_data": {"fields": []},
            }
            client.post("/api/v1/entity-schemas", json=data, headers=api_headers)
        resp = client.get("/api/v1/entity-schemas?page=1&page_size=2", headers=api_headers)
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total_count"] == 3


class TestGetEntitySchema:
    def test_get_success(self, client, api_headers, sample_schema_data):
        create_resp = client.post(
            "/api/v1/entity-schemas", json=sample_schema_data, headers=api_headers
        )
        sid = create_resp.json()["id"]
        resp = client.get(f"/api/v1/entity-schemas/{sid}", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["entity"] == "customer"

    def test_get_not_found(self, client, api_headers):
        resp = client.get("/api/v1/entity-schemas/999", headers=api_headers)
        assert resp.status_code == 404


class TestUpdateEntitySchema:
    def test_update_success(self, client, api_headers, sample_schema_data):
        create_resp = client.post(
            "/api/v1/entity-schemas", json=sample_schema_data, headers=api_headers
        )
        sid = create_resp.json()["id"]
        resp = client.put(
            f"/api/v1/entity-schemas/{sid}",
            json={"schema_data": {"fields": [{"name": "updated", "type": "string"}]}},
            headers=api_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["schema_data"]["fields"][0]["name"] == "updated"

    def test_update_entity_name(self, client, api_headers, sample_schema_data):
        create_resp = client.post(
            "/api/v1/entity-schemas", json=sample_schema_data, headers=api_headers
        )
        sid = create_resp.json()["id"]
        resp = client.put(
            f"/api/v1/entity-schemas/{sid}",
            json={"entity": "order"},
            headers=api_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["entity"] == "order"

    def test_update_not_found(self, client, api_headers):
        resp = client.put("/api/v1/entity-schemas/999", json={"entity": "x"}, headers=api_headers)
        assert resp.status_code == 404


class TestDeleteEntitySchema:
    def test_delete_success(self, client, api_headers, sample_schema_data):
        create_resp = client.post(
            "/api/v1/entity-schemas", json=sample_schema_data, headers=api_headers
        )
        sid = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/entity-schemas/{sid}", headers=api_headers)
        assert resp.status_code == 204

        get_resp = client.get(f"/api/v1/entity-schemas/{sid}", headers=api_headers)
        assert get_resp.status_code == 404

    def test_delete_not_found(self, client, api_headers):
        resp = client.delete("/api/v1/entity-schemas/999", headers=api_headers)
        assert resp.status_code == 404
