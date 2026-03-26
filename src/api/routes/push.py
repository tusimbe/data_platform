# src/api/routes/push.py
"""数据回写 API 路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key
from src.api.schemas.data import PushRequest, PushResponse
from src.services import push_service

router = APIRouter(dependencies=[Depends(get_current_api_key)])


@router.post("/push/{connector_type}/{entity}")
def push_data(
    connector_type: str,
    entity: str,
    data: PushRequest,
    session: Session = Depends(get_db),
) -> PushResponse:
    result = push_service.execute_push(connector_type, entity, data.records, session)
    return PushResponse(
        success_count=result.success_count,
        failure_count=result.failure_count,
        failures=result.failures,
    )
