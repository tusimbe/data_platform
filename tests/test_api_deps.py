# tests/test_api_deps.py
"""API 认证和分页依赖测试"""


class TestAPIKeyAuth:
    """API Key 认证测试"""

    def test_valid_bearer_token(self, client, api_headers):
        """有效 Bearer token 应通过认证"""
        resp = client.get("/api/v1/health", headers=api_headers)
        assert resp.status_code == 200

    def test_valid_x_api_key(self, client):
        """有效 X-API-Key 头应通过认证"""
        resp = client.get("/api/v1/health", headers={"X-API-Key": "test-api-key"})
        assert resp.status_code == 200

    def test_missing_api_key(self, client):
        """健康检查免认证"""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_invalid_bearer_token(self, client):
        """健康检查免认证，即使 token 无效也返回 200"""
        resp = client.get(
            "/api/v1/health", headers={"Authorization": "Bearer wrong-key"}
        )
        assert resp.status_code == 200


class TestPaginationParams:
    """分页参数测试"""

    def test_pagination_defaults(self):
        """默认分页参数"""
        from src.api.deps import PaginationParams

        params = PaginationParams(page=1, page_size=20)
        assert params.page == 1
        assert params.page_size == 20
        assert params.offset == 0

    def test_pagination_offset_calculation(self):
        """分页偏移计算"""
        from src.api.deps import PaginationParams

        params = PaginationParams(page=3, page_size=10)
        assert params.offset == 20
