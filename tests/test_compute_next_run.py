# tests/test_compute_next_run.py
"""_compute_next_run 纯函数测试"""
from datetime import datetime, timezone
from unittest.mock import patch


def test_compute_next_run_with_valid_cron():
    """有效 cron 表达式应返回未来的 datetime"""
    from src.services.sync_task_service import _compute_next_run

    result = _compute_next_run("*/30 * * * *")
    assert result is not None
    assert isinstance(result, datetime)
    assert result > datetime.now(timezone.utc)


def test_compute_next_run_none_cron():
    """cron_expression 为 None 应返回 None"""
    from src.services.sync_task_service import _compute_next_run

    result = _compute_next_run(None)
    assert result is None


def test_compute_next_run_empty_cron():
    """空字符串 cron_expression 应返回 None"""
    from src.services.sync_task_service import _compute_next_run

    result = _compute_next_run("")
    assert result is None


def test_compute_next_run_invalid_cron():
    """非法 cron 表达式应返回 None（不抛异常）"""
    from src.services.sync_task_service import _compute_next_run

    result = _compute_next_run("invalid cron expression")
    assert result is None
