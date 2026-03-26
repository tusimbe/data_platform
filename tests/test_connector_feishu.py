# tests/test_connector_feishu.py
import pytest
from unittest.mock import patch, MagicMock
import time

from src.connectors.feishu import FeishuConnector
from src.connectors.base import ConnectorPullError, connector_registry


@pytest.fixture
def feishu_config():
    return {
        "base_url": "https://open.feishu.cn",
        "app_id": "cli_test_app_id",
        "app_secret": "test_app_secret",
    }


@pytest.fixture
def connector(feishu_config):
    return FeishuConnector(config=feishu_config)


def test_feishu_registered():
    """飞书连接器应已注册到全局注册表"""
    cls = connector_registry.get("feishu")
    assert cls is FeishuConnector


def test_feishu_list_entities(connector):
    """应返回支持的实体列表"""
    entities = connector.list_entities()
    assert len(entities) >= 3
    names = [e.name for e in entities]
    assert "employee" in names
    assert "department" in names
    assert "approval" in names


def test_feishu_health_check_success(connector):
    """健康检查成功时应返回 healthy"""
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = {"code": 0}
        result = connector.health_check()
        assert result.status == "healthy"


def test_feishu_health_check_failure(connector):
    """健康检查失败时应返回 unhealthy"""
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("Connection refused")
        result = connector.health_check()
        assert result.status == "unhealthy"


def test_feishu_pull_success(connector):
    """拉取数据成功应返回字典列表"""
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200
    mock_response = {
        "code": 0,
        "data": {
            "items": [
                {"user_id": "ou_001", "name": "张三", "department_id": "d001"},
                {"user_id": "ou_002", "name": "李四", "department_id": "d001"},
            ]
        },
    }
    with patch.object(connector, "_request") as mock_req:
        mock_req.return_value = mock_response
        records = connector.pull(entity="employee")
        assert len(records) == 2
        assert records[0]["user_id"] == "ou_001"


def test_feishu_pull_failure(connector):
    """拉取数据失败应抛出 ConnectorPullError"""
    # 先设置 token 避免 _ensure_token 调用 connect
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200
    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = Exception("API Error")
        with pytest.raises(ConnectorPullError):
            connector.pull(entity="employee")


def test_feishu_connect_gets_token(connector):
    """connect() 应获取 tenant_access_token"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": 0,
        "tenant_access_token": "t-test-token-123",
        "expire": 7200,
    }
    mock_resp.raise_for_status = MagicMock()
    with patch.object(connector._client, "request", return_value=mock_resp):
        connector.connect()
        assert connector._token == "t-test-token-123"


# Additional tests based on Task 1 feedback


def test_feishu_pull_invalid_entity_raises_error(connector):
    """拉取不支持的实体类型应抛出 ConnectorPullError"""
    with pytest.raises(ConnectorPullError) as exc_info:
        connector.pull(entity="invalid_entity")
    assert "不支持的实体类型" in str(exc_info.value)


def test_feishu_push_returns_all_failures(connector):
    """飞书不支持写入，push应返回所有记录失败"""
    records = [
        {"user_id": "ou_001", "name": "张三"},
        {"user_id": "ou_002", "name": "李四"},
        {"user_id": "ou_003", "name": "王五"},
    ]
    result = connector.push(entity="employee", records=records)
    assert result.success_count == 0
    assert result.failure_count == 3
    assert len(result.failures) == 3
    # 验证每个失败记录都有错误信息
    for failure in result.failures:
        assert "error" in failure
        assert "飞书不支持此实体的写入" in failure["error"]


def test_feishu_pull_pagination(connector):
    """拉取数据应支持分页，获取所有页面的数据"""
    # 先设置 token 避免 _ensure_token 调用 connect
    connector._token = "test-token"
    connector._token_expires_at = time.time() + 7200

    # 模拟分页响应：第一页有 page_token，第二页没有
    page1_response = {
        "code": 0,
        "data": {
            "items": [
                {"user_id": "ou_001", "name": "张三"},
                {"user_id": "ou_002", "name": "李四"},
            ],
            "page_token": "next_page_token_123",
        },
    }
    page2_response = {
        "code": 0,
        "data": {
            "items": [
                {"user_id": "ou_003", "name": "王五"},
            ],
            # 没有 page_token 表示最后一页
        },
    }

    with patch.object(connector, "_request") as mock_req:
        mock_req.side_effect = [page1_response, page2_response]
        records = connector.pull(entity="employee")

        # 应该合并两页的数据
        assert len(records) == 3
        assert records[0]["user_id"] == "ou_001"
        assert records[1]["user_id"] == "ou_002"
        assert records[2]["user_id"] == "ou_003"

        # 验证第二次请求包含 page_token
        assert mock_req.call_count == 2
        second_call_params = mock_req.call_args_list[1][1]["params"]
        assert second_call_params.get("page_token") == "next_page_token_123"


def test_feishu_pull_max_pages_cap(connector):
    from src.connectors.feishu import MAX_PAGES

    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return {
            "code": 0,
            "data": {
                "items": [{"id": f"emp-{call_count}"}],
                "page_token": f"token_{call_count}",
            },
        }

    connector._token = "test-token"
    connector._token_expires_at = __import__("time").time() + 7200
    with patch.object(connector, "_request", side_effect=mock_request):
        records = connector.pull(entity="employee")

    assert call_count == MAX_PAGES
    assert len(records) == MAX_PAGES
