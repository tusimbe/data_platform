# src/api/routes/connectors.py
"""连接器管理 API 路由"""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key, PaginationParams
from src.api.schemas.connector import ConnectorCreate, ConnectorUpdate
from src.services import connector_service

router = APIRouter(dependencies=[Depends(get_current_api_key)])


@router.get("/connectors")
def list_connectors(
    params: PaginationParams = Depends(),
    session: Session = Depends(get_db),
):
    result = connector_service.list_connectors(session, params)
    result["items"] = [connector_service.connector_to_response(c) for c in result["items"]]
    return result


@router.post("/connectors", status_code=201)
def create_connector(
    data: ConnectorCreate,
    session: Session = Depends(get_db),
):
    connector = connector_service.create_connector(session, data.model_dump())
    session.commit()
    return connector_service.connector_to_response(connector)


@router.get("/connectors/{connector_id}")
def get_connector(
    connector_id: int,
    session: Session = Depends(get_db),
):
    connector = connector_service.get_connector(session, connector_id)
    return connector_service.connector_to_response(connector)


@router.put("/connectors/{connector_id}")
def update_connector(
    connector_id: int,
    data: ConnectorUpdate,
    session: Session = Depends(get_db),
):
    connector = connector_service.update_connector(
        session, connector_id, data.model_dump(exclude_unset=True)
    )
    session.commit()
    return connector_service.connector_to_response(connector)


@router.delete("/connectors/{connector_id}", status_code=204)
def delete_connector(
    connector_id: int,
    session: Session = Depends(get_db),
):
    connector_service.delete_connector(session, connector_id)
    session.commit()
    return Response(status_code=204)
