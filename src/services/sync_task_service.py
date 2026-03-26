# src/services/sync_task_service.py
"""同步任务管理服务：CRUD + 验证 + 触发执行 + 日志查询"""
from datetime import datetime, timezone

from croniter import croniter
from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.api.deps import PaginationParams, paginate
from src.models.connector import Connector
from src.models.sync import SyncTask, SyncLog


def list_sync_tasks(session: Session, params: PaginationParams) -> dict:
    """分页列出同步任务"""
    query = session.query(SyncTask).order_by(SyncTask.id)
    return paginate(query, params)


def get_sync_task(session: Session, task_id: int) -> SyncTask:
    """按 ID 获取同步任务"""
    task = session.query(SyncTask).filter_by(id=task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Sync task with id {task_id} not found")
    return task


def create_sync_task(session: Session, data: dict) -> SyncTask:
    """创建同步任务，验证 connector_id 和 entity"""
    # 验证 connector 存在且启用
    connector = session.query(Connector).filter_by(id=data["connector_id"]).first()
    if not connector or not connector.enabled:
        raise HTTPException(status_code=400, detail="Connector not found or disabled")

    task = SyncTask(
        connector_id=data["connector_id"],
        entity=data["entity"],
        direction=data["direction"],
        cron_expression=data.get("cron_expression"),
        enabled=data.get("enabled", True),
    )
    session.add(task)
    session.flush()
    return task


def update_sync_task(session: Session, task_id: int, data: dict) -> SyncTask:
    """更新同步任务"""
    task = get_sync_task(session, task_id)
    for key, value in data.items():
        if value is not None and hasattr(task, key):
            setattr(task, key, value)
    session.flush()
    return task


def delete_sync_task(session: Session, task_id: int) -> None:
    """删除同步任务"""
    task = get_sync_task(session, task_id)
    session.delete(task)
    session.flush()


def trigger_sync(session: Session, task_id: int) -> dict:
    """手动触发同步：验证后入队 Celery task"""
    task = get_sync_task(session, task_id)
    if not task.enabled:
        raise HTTPException(status_code=400, detail="Sync task is disabled")

    connector = session.query(Connector).filter_by(id=task.connector_id).first()
    if not connector or not connector.enabled:
        raise HTTPException(status_code=400, detail="Associated connector not found or disabled")

    from src.tasks.sync_tasks import run_sync_task
    result = run_sync_task.delay(task_id)
    return {
        "status": "accepted",
        "task_id": task_id,
        "celery_task_id": result.id,
        "message": "Sync task has been queued",
    }


def list_sync_logs(
    session: Session,
    params: PaginationParams,
    connector_id: int | None = None,
    entity: str | None = None,
    status: str | None = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
) -> dict:
    """分页查询同步日志，支持过滤"""
    query = session.query(SyncLog).order_by(SyncLog.started_at.desc())
    if connector_id is not None:
        query = query.filter(SyncLog.connector_id == connector_id)
    if entity is not None:
        query = query.filter(SyncLog.entity == entity)
    if status is not None:
        query = query.filter(SyncLog.status == status)
    if started_after is not None:
        query = query.filter(SyncLog.started_at >= started_after)
    if started_before is not None:
        query = query.filter(SyncLog.started_at <= started_before)
    return paginate(query, params)


def sync_task_to_response(task: SyncTask) -> dict:
    """将 SyncTask ORM 转为响应字典"""
    return {
        "id": task.id,
        "connector_id": task.connector_id,
        "entity": task.entity,
        "direction": task.direction,
        "cron_expression": task.cron_expression,
        "enabled": task.enabled,
        "last_sync_at": task.last_sync_at,
        "next_run_at": _compute_next_run(task.cron_expression),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def sync_log_to_response(log: SyncLog) -> dict:
    """将 SyncLog ORM 转为响应字典"""
    return {
        "id": log.id,
        "sync_task_id": log.sync_task_id,
        "connector_id": log.connector_id,
        "entity": log.entity,
        "direction": log.direction,
        "status": log.status,
        "total_records": log.total_records,
        "success_count": log.success_count,
        "failure_count": log.failure_count,
        "error_details": log.error_details,
        "started_at": log.started_at,
        "finished_at": log.finished_at,
    }


def _compute_next_run(cron_expression: str | None) -> datetime | None:
    """从 cron 表达式计算下次运行时间。无 cron 或非法表达式返回 None。"""
    if not cron_expression:
        return None
    try:
        cron = croniter(cron_expression, datetime.now(timezone.utc))
        return cron.get_next(datetime)
    except (ValueError, KeyError, TypeError):
        return None

