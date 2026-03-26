# tests/test_api_push.py
"""数据回写 API 测试"""
import pytest
from unittest.mock import patch, MagicMock
from src.models.connector import Connector
from src.connectors.base import PushResult, ConnectorError


@pytest.fixture
def connector_in_db(db_session):
    c = Connector(
        name="推送测试连接器",
        connector_type="kingdee_erp",
        base_url="https://erp.test.com",
        auth_config={"test": True},
        enabled=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


class TestPushData:
    def test_push_success(self, client, api_headers, connector_in_db):
        mock_connector = MagicMock()
        mock_connector.push.return_value = PushResult(success_count=2, failure_count=0, failures=[])
        mock_class = MagicMock(return_value=mock_connector)

        with patch("src.services.push_service.connector_registry") as mock_registry:
            mock_registry.get.return_value = mock_class
            resp = client.post(
                "/api/v1/push/kingdee_erp/order",
                json={"records": [{"name": "A"}, {"name": "B"}]},
                headers=api_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success_count"] == 2
        assert data["failure_count"] == 0

    def test_push_no_connector(self, client, api_headers):
        resp = client.post(
            "/api/v1/push/nonexistent/order",
            json={"records": [{"name": "A"}]},
            headers=api_headers,
        )
        assert resp.status_code == 404

    def test_push_connector_unavailable(self, client, api_headers, connector_in_db):
        mock_connector = MagicMock()
        mock_connector.connect.side_effect = ConnectorError("Connection refused")
        mock_class = MagicMock(return_value=mock_connector)

        with patch("src.services.push_service.connector_registry") as mock_registry:
            mock_registry.get.return_value = mock_class
            resp = client.post(
                "/api/v1/push/kingdee_erp/order",
                json={"records": [{"name": "A"}]},
                headers=api_headers,
            )
        assert resp.status_code == 502

    def test_push_empty_records(self, client, api_headers, connector_in_db):
        resp = client.post(
            "/api/v1/push/kingdee_erp/order",
            json={"records": []},
            headers=api_headers,
        )
        assert resp.status_code == 422  # min_length=1 validation

    def test_push_partial_failure(self, client, api_headers, connector_in_db):
        mock_connector = MagicMock()
        mock_connector.push.return_value = PushResult(
            success_count=1, failure_count=1,
            failures=[{"record": {"name": "B"}, "error": "failed"}],
        )
        mock_class = MagicMock(return_value=mock_connector)

        with patch("src.services.push_service.connector_registry") as mock_registry:
            mock_registry.get.return_value = mock_class
            resp = client.post(
                "/api/v1/push/kingdee_erp/order",
                json={"records": [{"name": "A"}, {"name": "B"}]},
                headers=api_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success_count"] == 1
        assert data["failure_count"] == 1
        assert len(data["failures"]) == 1

    def test_push_requires_auth(self, client):
        resp = client.post("/api/v1/push/kingdee_erp/order", json={"records": [{"name": "A"}]})
        assert resp.status_code == 401
