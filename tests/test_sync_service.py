# tests/test_sync_service.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.services.sync_service import SyncExecutor

# 注意：此文件使用 conftest.py 中的 db_session fixture（SQLite 内存数据库）


@pytest.fixture
def mock_connector():
    conn = MagicMock()
    conn.pull.return_value = [
        {"FBillNo": "SO-001", "FDate": "2026-01-15", "FAmount": 1000},
        {"FBillNo": "SO-002", "FDate": "2026-01-16", "FAmount": 2000},
    ]
    return conn


@pytest.fixture
def mock_mappings():
    return [
        {"source_field": "FBillNo", "target_field": "order_number", "transform": None},
        {"source_field": "FDate", "target_field": "order_date", "transform": None},
        {"source_field": "FAmount", "target_field": "total_amount", "transform": None},
    ]


@pytest.fixture
def executor():
    return SyncExecutor()


def test_pull_phase(executor, mock_connector):
    """阶段1：拉取应调用 connector.pull 并返回原始数据"""
    records = executor.pull_phase(
        connector=mock_connector,
        entity="sales_order",
        since=None,
    )
    mock_connector.pull.assert_called_once_with(
        entity="sales_order", since=None, filters=None
    )
    assert len(records) == 2


def test_transform_phase(executor, mock_mappings):
    """阶段2：转换应将原始数据映射为统一格式"""
    raw_records = [
        {"FBillNo": "SO-001", "FDate": "2026-01-15", "FAmount": 1000},
    ]
    transformed, errors = executor.transform_phase(raw_records, mock_mappings)
    assert len(transformed) == 1
    assert len(errors) == 0
    assert transformed[0]["order_number"] == "SO-001"
    assert transformed[0]["total_amount"] == 1000


def test_transform_phase_with_error(executor):
    """阶段2：转换失败的记录应收集到错误列表"""
    mappings = [
        {
            "source_field": "FDate",
            "target_field": "date",
            "transform": "date_format",
            "transform_config": {"input": "%Y-%m-%d", "output": "%Y-%m-%d"},
        },
    ]
    records = [
        {"FDate": "2026-01-15"},  # 正确
        {"FDate": "invalid-date"},  # 会失败
    ]
    transformed, errors = executor.transform_phase(records, mappings)
    assert len(transformed) == 1
    assert len(errors) == 1
    assert "invalid-date" in str(errors[0])


def test_full_pull_sync(executor, mock_connector, mock_mappings, db_session):
    """完整拉取同步流程应存储数据并创建 SyncLog"""
    from src.models.connector import Connector
    from src.models.sync import SyncLog

    # 创建测试用连接器记录
    c = Connector(
        name="测试", connector_type="kingdee_erp", base_url="http://test",
        auth_config={}, enabled=True,
    )
    db_session.add(c)
    db_session.flush()

    result = executor.execute_pull(
        connector=mock_connector,
        connector_id=c.id,
        entity="sales_order",
        target_table="unified_orders",
        mappings=mock_mappings,
        session=db_session,
        since=None,
    )

    assert result["status"] == "success"
    assert result["total_records"] == 2
    assert result["success_count"] == 2
    assert result["failure_count"] == 0

    # 验证 SyncLog 已创建
    logs = db_session.query(SyncLog).filter_by(connector_id=c.id).all()
    assert len(logs) == 1
    assert logs[0].status == "success"
    assert logs[0].total_records == 2
    assert logs[0].success_count == 2
