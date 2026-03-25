# tests/test_api_health.py
"""健康检查 API 测试"""


def test_root(client):
    """根路径应返回应用信息"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "数据中台"


def test_health_endpoint(client):
    """健康检查端点应返回状态"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in ("healthy", "degraded", "unhealthy")


def test_health_no_auth_required(client):
    """健康检查免认证"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
