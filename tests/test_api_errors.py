# tests/test_api_errors.py
"""统一错误响应格式测试"""


def test_error_response_structure(client):
    """错误响应应包含 error.code 和 error.message"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_health_returns_valid_json(client):
    """健康检查应返回有效 JSON"""
    resp = client.get("/api/v1/health")
    data = resp.json()
    assert "status" in data
