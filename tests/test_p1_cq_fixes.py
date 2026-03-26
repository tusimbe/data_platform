from unittest.mock import MagicMock, patch

from src.api.errors import DOMAIN_EXCEPTION_MAP
from src.core.entity_registry import (
    get_entity_id_field,
    get_entity_model,
    get_entity_table,
)
from src.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    NotImplementedError_,
    ServiceUnavailableError,
    ValidationError,
)
from src.models.unified import UnifiedCustomer


def test_app_error_base_defaults():
    exc = AppError("msg")

    assert exc.message == "msg"
    assert exc.details is None


def test_app_error_preserves_details():
    details = {"k": "v"}

    exc = AppError("msg", details=details)

    assert exc.message == "msg"
    assert exc.details == {"k": "v"}


def test_not_found_error_is_app_error():
    assert issubclass(NotFoundError, AppError)


def test_conflict_error_is_app_error():
    assert issubclass(ConflictError, AppError)


def test_validation_error_is_app_error():
    assert issubclass(ValidationError, AppError)


def test_service_unavailable_error_is_app_error():
    assert issubclass(ServiceUnavailableError, AppError)


def test_not_implemented_error_is_app_error():
    assert issubclass(NotImplementedError_, AppError)


def test_domain_exception_map_not_found_mapping():
    assert DOMAIN_EXCEPTION_MAP[NotFoundError] == (404, "NOT_FOUND")


def test_domain_exception_map_conflict_mapping():
    assert DOMAIN_EXCEPTION_MAP[ConflictError] == (409, "CONFLICT")


def test_domain_exception_map_validation_mapping():
    assert DOMAIN_EXCEPTION_MAP[ValidationError] == (400, "BAD_REQUEST")


def test_domain_exception_map_service_unavailable_mapping():
    assert DOMAIN_EXCEPTION_MAP[ServiceUnavailableError] == (502, "BAD_GATEWAY")


def test_domain_exception_map_not_implemented_mapping():
    assert DOMAIN_EXCEPTION_MAP[NotImplementedError_] == (501, "NOT_IMPLEMENTED")


def test_nonexistent_connector_returns_not_found_error_code(client, api_headers):
    response = client.get("/api/v1/connectors/999999", headers=api_headers)

    assert response.status_code == 404
    payload = response.json()
    assert "error" in payload
    assert payload["error"]["code"] == "NOT_FOUND"


def test_get_entity_table_customer():
    assert get_entity_table("customer") == "unified_customers"


def test_get_entity_table_sales_order():
    assert get_entity_table("sales_order") == "unified_orders"


def test_get_entity_table_unknown_fallback():
    assert get_entity_table("unknown_xyz") == "unified_unknown_xyz"


def test_get_entity_model_known_table_returns_unified_customer():
    assert get_entity_model("unified_customers") is UnifiedCustomer


def test_get_entity_model_unknown_returns_none():
    assert get_entity_model("nonexistent_table") is None


def test_get_entity_id_field_customer():
    assert get_entity_id_field("customer") == "id"


def test_get_entity_id_field_sales_order():
    assert get_entity_id_field("sales_order") == "FBillNo"


def test_get_entity_id_field_unknown_fallback():
    assert get_entity_id_field("unknown") == "id"


def _mock_health_dependencies(mock_redis_from_url, mock_celery_app):
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis_from_url.return_value = mock_redis

    mock_celery_app.control.ping.return_value = [{"worker1": {"ok": "pong"}}]


@patch("src.core.celery_app.celery_app")
@patch("src.api.routes.health.redis.from_url")
def test_public_health_no_auth_returns_status_only(
    mock_redis_from_url,
    mock_celery_app,
    client,
):
    _mock_health_dependencies(mock_redis_from_url, mock_celery_app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"status"}


@patch("src.core.celery_app.celery_app")
@patch("src.api.routes.health.redis.from_url")
def test_public_health_response_has_exactly_one_key(
    mock_redis_from_url,
    mock_celery_app,
    client,
):
    _mock_health_dependencies(mock_redis_from_url, mock_celery_app)

    response = client.get("/api/v1/health")

    body = response.json()
    assert "status" in body
    assert "components" not in body
    assert "version" not in body
    assert len(body) == 1


def test_health_detail_requires_auth(client):
    response = client.get("/api/v1/health/detail")

    assert response.status_code == 401


@patch("src.core.celery_app.celery_app")
@patch("src.api.routes.health.redis.from_url")
def test_health_detail_with_auth_returns_status_components_and_version(
    mock_redis_from_url,
    mock_celery_app,
    client,
    api_headers,
):
    _mock_health_dependencies(mock_redis_from_url, mock_celery_app)

    response = client.get("/api/v1/health/detail", headers=api_headers)

    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "components" in body
    assert "version" in body


@patch("src.core.celery_app.celery_app")
@patch("src.api.routes.health.redis.from_url")
def test_health_detail_components_include_database_redis_celery(
    mock_redis_from_url,
    mock_celery_app,
    client,
    api_headers,
):
    _mock_health_dependencies(mock_redis_from_url, mock_celery_app)

    response = client.get("/api/v1/health/detail", headers=api_headers)

    assert response.status_code == 200
    components = response.json()["components"]
    assert "database" in components
    assert "redis" in components
    assert "celery" in components
