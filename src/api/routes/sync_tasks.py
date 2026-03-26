# src/api/routes/sync_tasks.py
"""同步任务管理 API 路由"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key, PaginationParams
from src.api.schemas.sync import SyncTaskCreate, SyncTaskUpdate
from src.services import sync_task_service

router = APIRouter(dependencies=[Depends(get_current_api_key)])


@router.get("/sync-tasks")
def list_sync_tasks(
    params: PaginationParams = Depends(),
    session: Session = Depends(get_db),
):
    result = sync_task_service.list_sync_tasks(session, params)
    result["items"] = [sync_task_service.sync_task_to_response(t) for t in result["items"]]
    return result


@router.post("/sync-tasks", status_code=201)
def create_sync_task(
    data: SyncTaskCreate,
    session: Session = Depends(get_db),
):
    task = sync_task_service.create_sync_task(session, data.model_dump())
    session.commit()
    return sync_task_service.sync_task_to_response(task)


@router.get("/sync-tasks/{task_id}")
def get_sync_task(
    task_id: int,
    session: Session = Depends(get_db),
):
    task = sync_task_service.get_sync_task(session, task_id)
    return sync_task_service.sync_task_to_response(task)


@router.put("/sync-tasks/{task_id}")
def update_sync_task(
    task_id: int,
    data: SyncTaskUpdate,
    session: Session = Depends(get_db),
):
    task = sync_task_service.update_sync_task(session, task_id, data.model_dump(exclude_unset=True))
    session.commit()
    return sync_task_service.sync_task_to_response(task)


@router.delete("/sync-tasks/{task_id}", status_code=204)
def delete_sync_task(
    task_id: int,
    session: Session = Depends(get_db),
):
    sync_task_service.delete_sync_task(session, task_id)
    session.commit()
    return Response(status_code=204)


@router.post("/sync-tasks/{task_id}/trigger")
def trigger_sync(
    task_id: int,
    session: Session = Depends(get_db),
):
    result = sync_task_service.trigger_sync(session, task_id)
    session.commit()
    return result
