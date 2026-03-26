# tests/test_api_health.py
"""增强版健康检查 API 测试"""


def test_root(client):
    """根路径应返回应用信息"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "数据中台"


def test_health_returns_status(client):
    """健康检查应返回 overall status"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded", "unhealthy")


def test_health_has_components(client):
    """健康检查应包含所有组件状态"""
    resp = client.get("/api/v1/health")
    data = resp.json()
    assert "database" in data["components"]
    assert "redis" in data["components"]
    assert "celery" in data["components"]


def test_health_database_latency(client):
    """数据库健康检查应返回延迟"""
    resp = client.get("/api/v1/health")
    db = resp.json()["components"]["database"]
    assert db["status"] == "healthy"
    assert "latency_ms" in db


def test_health_no_auth_required(client):
    """健康检查端点不需要认证"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_health_has_version(client):
    """健康检查应返回版本号"""
    resp = client.get("/api/v1/health")
    assert resp.json()["version"] == "0.1.0"


def test_health_redis_not_configured(client):
    """Redis 当前应为 not_configured"""
    resp = client.get("/api/v1/health")
    assert resp.json()["components"]["redis"]["status"] == "not_configured"
