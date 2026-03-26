# tests/test_api_health.py
"""增强版健康检查 API 测试"""


def test_root(client):
    """根路径应返回应用信息"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "数据中台"


def test_health_returns_status(client, mocker):
    """健康检查应返回 overall status"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_health_has_components(client, mocker):
    """健康检查应包含所有组件状态"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    data = resp.json()
    assert "database" in data["components"]
    assert "redis" in data["components"]
    assert "celery" in data["components"]


def test_health_database_latency(client, mocker):
    """数据库健康检查应返回延迟"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    db = resp.json()["components"]["database"]
    assert db["status"] == "healthy"
    assert "latency_ms" in db


def test_health_no_auth_required(client, mocker):
    """健康检查端点不需要认证"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_health_has_version(client, mocker):
    """健康检查应返回版本号"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    assert resp.json()["version"] == "0.1.0"


def test_health_redis_healthy(client, mocker):
    """Redis healthy 时应在组件中反映"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 2.5})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    redis_status = resp.json()["components"]["redis"]
    assert redis_status["status"] == "healthy"
    assert redis_status["latency_ms"] == 2.5


def test_health_redis_down_degraded(client, mocker):
    """Redis 不可用时 overall 应为 degraded"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "unhealthy", "error": "Connection refused"})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "healthy", "workers": 1, "latency_ms": 5.0})
    resp = client.get("/api/v1/health")
    assert resp.json()["status"] == "degraded"


def test_health_celery_down_degraded(client, mocker):
    """Celery 不可用时 overall 应为 degraded"""
    mocker.patch("src.api.routes.health._check_redis", return_value={"status": "healthy", "latency_ms": 1.0})
    mocker.patch("src.api.routes.health._check_celery", return_value={"status": "unhealthy", "error": "No workers"})
    resp = client.get("/api/v1/health")
    assert resp.json()["status"] == "degraded"
