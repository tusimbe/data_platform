# tests/test_connector_zentao.py
import pytest
from unittest.mock import patch, MagicMock
import time

from src.connectors.base import (
    HealthStatus,
    EntityInfo,
    PushResult,
    ConnectorPullError,
    ConnectorPushError,
    connector_registry,
)


@pytest.fixture
def zentao_config():
    return {
        "base_url": "https://zentao.example.com",
        "username": "admin",
        "password": "secret123",
    }


@pytest.fixture
def connector(zentao_config):
    from src.connectors.zentao import ZentaoConnector

    return ZentaoConnector(config=zentao_config)


def test_zentao_registered():
    """禅道连接器应已注册到全局注册表"""
    from src.connectors.zentao import ZentaoConnector

    cls = connector_registry.get("zentao")
    assert cls is ZentaoConnector


def test_zentao_list_entities(connector):
    """应返回支持的实体列表：project, story, task, bug"""
    entities = connector.list_entities()
    assert len(entities) == 4
    names = [e.name for e in entities]
    assert "project" in names
    assert "story" in names
    assert "task" in names
    assert "bug" in names


def test_zentao_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    connector._token = "test-session-token"
    connector._token_expires_at = time.time() + 7200
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"success": True}
        result = connector.health_check()
        assert result.status == "healthy"
        assert result.latency_ms is not None


def test_zentao_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    connector._token = "test-session-token"
    connector._token_expires_at = time.time() + 7200
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"
        assert result.error is not None
        assert "Connection refused" in result.error


def test_zentao_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    connector._token = "test-session-token"
    connector._token_expires_at = time.time() + 7200

    mock_response = {
        "success": True,
        "projects": [
            {"id": 1, "name": "项目A", "status": "active"},
            {"id": 2, "name": "项目B", "status": "closed"},
        ],
        "total": 2,
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="project")
        assert len(records) == 2
        assert records[0]["id"] == 1
        assert records[1]["name"] == "项目B"


def test_zentao_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    connector._token = "test-session-token"
    connector._token_expires_at = time.time() + 7200

    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"success": False, "message": "Internal Server Error"}
        with pytest.raises(ConnectorPullError) as exc_info:
            connector.pull(entity="project")
        assert "Internal Server Error" in str(exc_info.value)


def test_zentao_pull_invalid_entity_raises_error(connector):
    """拉取不支持的实体类型应抛出 ConnectorPullError"""
    with pytest.raises(ConnectorPullError) as exc_info:
        connector.pull(entity="invalid_entity")
    assert "不支持的实体类型" in str(exc_info.value)


def test_zentao_connect_gets_token(connector):
    """connect() 应通过 /api.php/v1/tokens 获取 session token"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True,
        "token": "session-token-abc123",
    }
    mock_resp.raise_for_status = MagicMock()
    with patch.object(connector._client, "request", return_value=mock_resp):
        connector.connect()
        assert connector._token == "session-token-abc123"


def test_zentao_push_success(connector):
    """推送数据成功应返回正确的 PushResult"""
    connector._token = "test-session-token"
    connector._token_expires_at = time.time() + 7200

    records = [
        {"name": "任务A", "project": 1, "assignedTo": "user1"},
        {"name": "任务B", "project": 1, "assignedTo": "user2"},
    ]

    with patch.object(connector, "_request") as mock_req:
        # 两次调用都成功
        mock_req.return_value = {"success": True, "data": {"id": 100}}
        result = connector.push(entity="task", records=records)

        assert result.success_count == 2
        assert result.failure_count == 0
        assert len(result.failures) == 0


def test_zentao_push_partial_failure(connector):
    """推送部分失败应返回正确的成功和失败计数"""
    connector._token = "test-session-token"
    connector._token_expires_at = time.time() + 7200

    records = [
        {"name": "任务A", "project": 1},
        {"name": "任务B", "project": 1},
        {"name": "任务C", "project": 1},
    ]

    with patch.object(connector, "_request") as mock_req:
        # 第一个成功，第二个失败，第三个成功
        mock_req.side_effect = [
            {"success": True, "data": {"id": 101}},
            {"success": False, "message": "Invalid project"},
            {"success": True, "data": {"id": 103}},
        ]
        result = connector.push(entity="task", records=records)

        assert result.success_count == 2
        assert result.failure_count == 1
        assert len(result.failures) == 1
        assert "Invalid project" in result.failures[0]["error"]


def test_zentao_pull_pagination(connector):
    """拉取数据应支持 limit+offset 分页，获取所有页面的数据"""
    connector._token = "test-session-token"
    connector._token_expires_at = time.time() + 7200

    # 模拟分页响应：第一页100条，第二页50条（小于limit表示最后一页）
    page1_response = {
        "success": True,
        "stories": [{"id": i, "name": f"需求{i}"} for i in range(1, 101)],
        "total": 150,
    }
    page2_response = {
        "success": True,
        "stories": [{"id": i, "name": f"需求{i}"} for i in range(101, 151)],
        "total": 150,
    }

    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = [page1_response, page2_response]
        records = connector.pull(entity="story")

        # 应该合并两页的数据
        assert len(records) == 150
        assert records[0]["id"] == 1
        assert records[99]["id"] == 100
        assert records[100]["id"] == 101
        assert records[149]["id"] == 150

        # 验证分页请求
        assert mock_req.call_count == 2


def test_zentao_disconnect(connector):
    """disconnect() 应清除 token"""
    connector._token = "test-session-token"
    connector._token_expires_at = time.time() + 7200

    connector.disconnect()

    assert connector._token is None
    assert connector._token_expires_at == 0


def test_zentao_get_schema(connector):
    """get_schema() 应返回实体配置信息"""
    schema = connector.get_schema("project")
    assert "path" in schema or "description" in schema

    # 不存在的实体应返回空字典
    empty_schema = connector.get_schema("nonexistent")
    assert empty_schema == {}


def test_zentao_push_invalid_entity_raises_error(connector):
    """推送不支持的实体类型应抛出 ConnectorPushError"""
    connector._token = "test-session-token"
    connector._token_expires_at = time.time() + 7200

    with pytest.raises(ConnectorPushError) as exc_info:
        connector.push(entity="invalid_entity", records=[{"name": "test"}])
    assert "不支持的实体类型" in str(exc_info.value)


def test_zentao_pagination_params_use_limit_offset(connector):
    """分页参数应使用 limit 和 offset"""
    connector._token = "test-session-token"
    connector._token_expires_at = time.time() + 7200

    # 返回少于 limit 的数据，表示最后一页
    mock_response = {
        "success": True,
        "bugs": [{"id": 1, "title": "Bug1"}, {"id": 2, "title": "Bug2"}],
        "total": 2,
    }

    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        connector.pull(entity="bug")

        # 验证请求参数包含 limit 和 offset
        call_args = mock_req.call_args
        params = call_args[1].get("params", {})
        assert "limit" in params
        assert "offset" in params
        assert params["limit"] == 100  # DEFAULT_PAGE_SIZE
        assert params["offset"] == 0
