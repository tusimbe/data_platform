from fastapi.testclient import TestClient
from src.main import app


client = TestClient(app)


def test_root():
    """根路径应返回应用信息"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "数据中台"


def test_health_endpoint():
    """健康检查端点应返回状态"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in ("healthy", "degraded", "unhealthy")
