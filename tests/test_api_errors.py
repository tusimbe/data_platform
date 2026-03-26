# tests/test_api_errors.py
"""统一错误响应格式测试"""


def test_401_error_format(client):
    """401 应返回标准错误格式"""
    resp = client.get("/api/v1/connectors")
    assert resp.status_code == 401
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "message" in data["error"]


def test_404_error_format(client, api_headers):
    """404 应返回标准错误格式"""
    resp = client.get("/api/v1/connectors/999", headers=api_headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "NOT_FOUND"


def test_422_validation_error_format(client, api_headers):
    """422 验证错误应包含 details"""
    resp = client.post("/api/v1/connectors", json={}, headers=api_headers)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["details"] is not None


def test_error_response_has_consistent_structure(client, api_headers):
    """所有错误响应都应有 error.code, error.message, error.details"""
    resp = client.get("/api/v1/data/unknown_entity", headers=api_headers)
    data = resp.json()
    assert "error" in data
    error = data["error"]
    assert "code" in error
    assert "message" in error
    assert "details" in error
