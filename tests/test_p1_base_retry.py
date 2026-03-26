from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy.exc import DatabaseError, OperationalError

from src.connectors.base import BaseConnector, ConnectorError, HealthStatus, PushResult
from src.tasks.scheduler import DatabaseScheduler


class _TestConnector(BaseConnector):
    def __init__(self, config=None):
        super().__init__(config or {})
        self._client = httpx.Client(timeout=5.0)

    def connect(self):
        pass

    def disconnect(self):
        self._client.close()

    def health_check(self):
        return HealthStatus(status="healthy")

    def list_entities(self):
        return []

    def pull(self, entity, since=None, filters=None):
        return []

    def push(self, entity, records):
        return PushResult(success_count=0, failure_count=0)

    def get_schema(self, entity):
        return {}


class _PreparedHeaderConnector(_TestConnector):
    def _prepare_request(self, method: str, url: str, headers: dict, kwargs: dict) -> None:
        headers["X-Prepared"] = "true"


def _make_response(status_code, json_data=None, headers=None):
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        headers=headers or {},
        request=httpx.Request("GET", "http://test"),
    )


def _make_scheduler():
    mock_app = MagicMock()
    mock_app.conf = MagicMock()
    with patch.object(DatabaseScheduler, "setup_schedule"):
        scheduler = DatabaseScheduler(app=mock_app)
    return scheduler


def test_request_successful_response_returns_json():
    connector = _TestConnector()
    connector._client.request = MagicMock(return_value=_make_response(200, {"ok": True}))

    result = connector._request("GET", "http://example.com/api")

    assert result == {"ok": True}
    assert connector._client.request.call_count == 1


@patch("time.sleep")
def test_request_retries_on_timeout_then_succeeds(mock_sleep):
    connector = _TestConnector()
    connector._client.request = MagicMock(
        side_effect=[
            httpx.TimeoutException("t1"),
            httpx.TimeoutException("t2"),
            _make_response(200, {"done": 1}),
        ]
    )

    result = connector._request("GET", "http://example.com/api")

    assert result == {"done": 1}
    assert connector._client.request.call_count == 3
    assert mock_sleep.call_count == 2


@patch("time.sleep")
def test_request_timeout_exhausted_retries_raises(mock_sleep):
    connector = _TestConnector()
    connector._client.request = MagicMock(side_effect=httpx.TimeoutException("always timeout"))

    with pytest.raises(httpx.TimeoutException):
        connector._request("GET", "http://example.com/api")

    assert connector._client.request.call_count == connector.MAX_RETRIES
    assert mock_sleep.call_count == connector.MAX_RETRIES - 1


@patch("time.sleep")
def test_request_429_retries_then_succeeds(mock_sleep):
    connector = _TestConnector()
    connector._client.request = MagicMock(
        side_effect=[
            _make_response(429, {"error": "rate limit"}, headers={"Retry-After": "1"}),
            _make_response(429, {"error": "rate limit"}, headers={"Retry-After": "1"}),
            _make_response(200, {"ok": True}),
        ]
    )

    result = connector._request("GET", "http://example.com/api")

    assert result == {"ok": True}
    assert connector._client.request.call_count == 3
    assert mock_sleep.call_count == 2
    assert mock_sleep.call_args_list[0].args[0] == 1
    assert mock_sleep.call_args_list[1].args[0] == 1


@patch("time.sleep")
def test_request_429_exhausted_raises_connector_error(mock_sleep):
    connector = _TestConnector()
    connector._client.request = MagicMock(
        side_effect=[
            _make_response(429, {"error": "rate"}, headers={"Retry-After": "1"}),
            _make_response(429, {"error": "rate"}, headers={"Retry-After": "1"}),
            _make_response(429, {"error": "rate"}, headers={"Retry-After": "1"}),
        ]
    )

    with pytest.raises(ConnectorError, match="Request failed without captured error"):
        connector._request("GET", "http://example.com/api")

    assert connector._client.request.call_count == connector.MAX_RETRIES
    assert mock_sleep.call_count == connector.MAX_RETRIES


def test_prepare_request_hook_can_modify_headers():
    connector = _PreparedHeaderConnector()
    connector._client.request = MagicMock(return_value=_make_response(200, {"ok": True}))

    connector._request("GET", "http://example.com/api")

    call_kwargs = connector._client.request.call_args.kwargs
    assert call_kwargs["headers"]["X-Prepared"] == "true"


@patch("time.sleep")
def test_request_http_500_retries_then_succeeds(mock_sleep):
    connector = _TestConnector()
    connector._client.request = MagicMock(
        side_effect=[
            _make_response(500, {"error": "server"}),
            _make_response(500, {"error": "server"}),
            _make_response(200, {"ok": 1}),
        ]
    )

    result = connector._request("GET", "http://example.com/api")

    assert result == {"ok": 1}
    assert connector._client.request.call_count == 3
    assert mock_sleep.call_count == 2


def test_request_passes_through_provided_headers():
    connector = _TestConnector()
    connector._client.request = MagicMock(return_value=_make_response(200, {"ok": True}))

    connector._request("GET", "http://example.com/api", headers={"X-Custom": "val"})

    call_kwargs = connector._client.request.call_args.kwargs
    assert call_kwargs["headers"]["X-Custom"] == "val"


@patch("src.tasks.scheduler.get_session_local")
def test_sync_from_db_db_error_increments_failures_without_updating_last_sync(
    mock_get_session_local,
):
    scheduler = _make_scheduler()
    mock_session_cls = MagicMock()
    mock_session = MagicMock()
    mock_session.query.side_effect = OperationalError("conn failed", {}, None)
    mock_session_cls.return_value = mock_session
    mock_get_session_local.return_value = mock_session_cls

    scheduler._sync_from_db()

    assert scheduler._consecutive_failures == 1
    assert scheduler._last_sync == 0.0


@patch("src.tasks.scheduler.get_session_local")
def test_sync_from_db_three_consecutive_db_errors_clear_schedule(mock_get_session_local):
    scheduler = _make_scheduler()
    scheduler._schedule = {"existing": MagicMock()}
    mock_session_cls = MagicMock()
    mock_session = MagicMock()
    mock_session.query.side_effect = DatabaseError("db failed", {}, None)
    mock_session_cls.return_value = mock_session
    mock_get_session_local.return_value = mock_session_cls

    scheduler._sync_from_db()
    scheduler._sync_from_db()
    scheduler._sync_from_db()

    assert scheduler._consecutive_failures == 3
    assert scheduler._schedule == {}


@patch("src.tasks.scheduler.get_session_local")
def test_sync_from_db_success_resets_consecutive_failures(mock_get_session_local):
    scheduler = _make_scheduler()
    scheduler._consecutive_failures = 2
    mock_session_cls = MagicMock()
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.all.return_value = []
    mock_session_cls.return_value = mock_session
    mock_get_session_local.return_value = mock_session_cls

    scheduler._sync_from_db()

    assert scheduler._consecutive_failures == 0


@patch("src.tasks.scheduler.get_session_local")
def test_sync_from_db_generic_exception_updates_last_sync(mock_get_session_local):
    scheduler = _make_scheduler()
    mock_session_cls = MagicMock()
    mock_session = MagicMock()
    mock_session.query.side_effect = RuntimeError("unexpected")
    mock_session_cls.return_value = mock_session
    mock_get_session_local.return_value = mock_session_cls

    scheduler._sync_from_db()

    assert scheduler._last_sync > 0


def test_schedule_property_triggers_refresh_when_stale():
    scheduler = _make_scheduler()
    scheduler._last_sync = 0.0
    scheduler.sync_every = 0.01

    with patch.object(scheduler, "_sync_from_db") as mock_sync:
        _ = scheduler.schedule

    assert mock_sync.called
