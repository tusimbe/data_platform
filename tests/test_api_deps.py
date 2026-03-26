# tests/test_api_deps.py
"""API 认证和分页依赖测试"""


class TestAPIKeyAuth:
    def test_valid_bearer_token(self, client, api_headers):
        """有效 Bearer token 应通过认证"""
        resp = client.get("/api/v1/connectors", headers=api_headers)
        assert resp.status_code == 200

    def test_valid_x_api_key(self, client):
        """有效 X-API-Key 头应通过认证"""
        resp = client.get("/api/v1/connectors", headers={"X-API-Key": "test-api-key"})
        assert resp.status_code == 200

    def test_missing_api_key_returns_401(self, client):
        """缺少 API Key 应返回 401"""
        resp = client.get("/api/v1/connectors")
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"]["code"] == "UNAUTHORIZED"

    def test_invalid_bearer_token_returns_401(self, client):
        """无效 Bearer token 应返回 401"""
        resp = client.get("/api/v1/connectors", headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    def test_health_no_auth_required(self, client):
        """健康检查免认证"""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_empty_api_key_config_returns_500(self, client, db_session):
        from unittest.mock import patch, MagicMock

        mock_settings = MagicMock()
        mock_settings.API_KEY = ""
        with patch("src.api.deps.get_settings", return_value=mock_settings):
            resp = client.get("/api/v1/connectors", headers={"Authorization": "Bearer anything"})
            assert resp.status_code == 500


class TestPaginationParams:
    def test_pagination_defaults(self):
        from src.api.deps import PaginationParams

        params = PaginationParams(page=1, page_size=20)
        assert params.page == 1
        assert params.page_size == 20
        assert params.offset == 0

    def test_pagination_offset_calculation(self):
        from src.api.deps import PaginationParams

        params = PaginationParams(page=3, page_size=10)
        assert params.offset == 20


def test_cors_preflight_returns_allow_headers(client):
    resp = client.options(
        "/api/v1/connectors",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
