import pytest


@pytest.fixture
def sample_mapping_data():
    return {
        "connector_type": "fenxiangxiaoke",
        "source_entity": "customer",
        "target_table": "unified_customers",
        "source_field": "account_name",
        "target_field": "name",
    }


@pytest.fixture
def mapping_with_transform():
    return {
        "connector_type": "fenxiangxiaoke",
        "source_entity": "customer",
        "target_table": "unified_customers",
        "source_field": "create_time",
        "target_field": "created_date",
        "transform": "date_format",
        "transform_config": {"input": "%Y%m%d", "output": "%Y-%m-%d"},
    }


class TestCreateFieldMapping:
    def test_create_success(self, client, api_headers, sample_mapping_data):
        resp = client.post("/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["connector_type"] == "fenxiangxiaoke"
        assert data["source_field"] == "account_name"
        assert data["target_field"] == "name"
        assert data["transform"] is None
        assert data["transform_config"] is None
        assert "id" in data
        assert "created_at" in data

    def test_create_with_transform(self, client, api_headers, mapping_with_transform):
        resp = client.post(
            "/api/v1/field-mappings", json=mapping_with_transform, headers=api_headers
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["transform"] == "date_format"
        assert data["transform_config"]["input"] == "%Y%m%d"

    def test_create_invalid_transform(self, client, api_headers, sample_mapping_data):
        sample_mapping_data["transform"] = "invalid_transform"
        resp = client.post("/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers)
        assert resp.status_code == 400

    def test_create_duplicate(self, client, api_headers, sample_mapping_data):
        client.post("/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers)
        resp = client.post("/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers)
        assert resp.status_code == 409

    def test_create_requires_auth(self, client, sample_mapping_data):
        resp = client.post("/api/v1/field-mappings", json=sample_mapping_data)
        assert resp.status_code == 401

    def test_create_missing_required_field(self, client, api_headers):
        resp = client.post(
            "/api/v1/field-mappings", json={"connector_type": "x"}, headers=api_headers
        )
        assert resp.status_code == 422


class TestListFieldMappings:
    def test_list_empty(self, client, api_headers):
        resp = client.get("/api/v1/field-mappings", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total_count"] == 0

    def test_list_with_data(self, client, api_headers, sample_mapping_data):
        client.post("/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers)
        resp = client.get("/api/v1/field-mappings", headers=api_headers)
        data = resp.json()
        assert data["total_count"] == 1
        assert len(data["items"]) == 1

    def test_list_filter_by_connector_type(self, client, api_headers, sample_mapping_data):
        client.post("/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers)
        other = {**sample_mapping_data, "connector_type": "kingdee_erp", "source_field": "FName"}
        client.post("/api/v1/field-mappings", json=other, headers=api_headers)

        resp = client.get(
            "/api/v1/field-mappings?connector_type=fenxiangxiaoke", headers=api_headers
        )
        data = resp.json()
        assert data["total_count"] == 1
        assert data["items"][0]["connector_type"] == "fenxiangxiaoke"

    def test_list_filter_by_source_entity(self, client, api_headers, sample_mapping_data):
        client.post("/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers)
        other = {**sample_mapping_data, "source_entity": "order", "source_field": "order_no"}
        client.post("/api/v1/field-mappings", json=other, headers=api_headers)

        resp = client.get("/api/v1/field-mappings?source_entity=customer", headers=api_headers)
        data = resp.json()
        assert data["total_count"] == 1

    def test_list_pagination(self, client, api_headers, sample_mapping_data):
        for i in range(3):
            m = {**sample_mapping_data, "source_field": f"field_{i}"}
            client.post("/api/v1/field-mappings", json=m, headers=api_headers)
        resp = client.get("/api/v1/field-mappings?page=1&page_size=2", headers=api_headers)
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total_count"] == 3


class TestGetFieldMapping:
    def test_get_success(self, client, api_headers, sample_mapping_data):
        create_resp = client.post(
            "/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers
        )
        mid = create_resp.json()["id"]
        resp = client.get(f"/api/v1/field-mappings/{mid}", headers=api_headers)
        assert resp.status_code == 200
        assert resp.json()["source_field"] == "account_name"

    def test_get_not_found(self, client, api_headers):
        resp = client.get("/api/v1/field-mappings/999", headers=api_headers)
        assert resp.status_code == 404


class TestUpdateFieldMapping:
    def test_update_success(self, client, api_headers, sample_mapping_data):
        create_resp = client.post(
            "/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers
        )
        mid = create_resp.json()["id"]
        resp = client.put(
            f"/api/v1/field-mappings/{mid}",
            json={"target_field": "display_name"},
            headers=api_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["target_field"] == "display_name"

    def test_update_add_transform(self, client, api_headers, sample_mapping_data):
        create_resp = client.post(
            "/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers
        )
        mid = create_resp.json()["id"]
        resp = client.put(
            f"/api/v1/field-mappings/{mid}",
            json={"transform": "value_map", "transform_config": {"map": {"A": "Active"}}},
            headers=api_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["transform"] == "value_map"

    def test_update_invalid_transform(self, client, api_headers, sample_mapping_data):
        create_resp = client.post(
            "/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers
        )
        mid = create_resp.json()["id"]
        resp = client.put(
            f"/api/v1/field-mappings/{mid}",
            json={"transform": "bad_transform"},
            headers=api_headers,
        )
        assert resp.status_code == 400

    def test_update_not_found(self, client, api_headers):
        resp = client.put(
            "/api/v1/field-mappings/999", json={"target_field": "x"}, headers=api_headers
        )
        assert resp.status_code == 404


class TestDeleteFieldMapping:
    def test_delete_success(self, client, api_headers, sample_mapping_data):
        create_resp = client.post(
            "/api/v1/field-mappings", json=sample_mapping_data, headers=api_headers
        )
        mid = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/field-mappings/{mid}", headers=api_headers)
        assert resp.status_code == 204

        get_resp = client.get(f"/api/v1/field-mappings/{mid}", headers=api_headers)
        assert get_resp.status_code == 404

    def test_delete_not_found(self, client, api_headers):
        resp = client.delete("/api/v1/field-mappings/999", headers=api_headers)
        assert resp.status_code == 404
