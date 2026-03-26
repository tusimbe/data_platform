# src/api/routes/sync_logs.py
"""同步日志查询 API 路由"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key, PaginationParams
from src.services import sync_task_service

router = APIRouter(dependencies=[Depends(get_current_api_key)])


@router.get("/sync-logs")
def list_sync_logs(
    params: PaginationParams = Depends(),
    connector_id: int | None = Query(None),
    entity: str | None = Query(None),
    status: str | None = Query(None),
    started_after: datetime | None = Query(None),
    started_before: datetime | None = Query(None),
    session: Session = Depends(get_db),
):
    result = sync_task_service.list_sync_logs(
        session, params,
        connector_id=connector_id,
        entity=entity,
        status=status,
        started_after=started_after,
        started_before=started_before,
    )
    result["items"] = [sync_task_service.sync_log_to_response(log) for log in result["items"]]
    return result
