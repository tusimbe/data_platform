from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.deps import PaginationParams, get_current_api_key, get_db
from src.api.schemas.flow import (
    FlowDefinitionCreate,
    FlowDefinitionResponse,
    FlowDefinitionUpdate,
    FlowInstanceCreate,
    FlowInstanceResponse,
)
from src.services import flow_service

router = APIRouter(dependencies=[Depends(get_current_api_key)])


def _definition_to_response(definition) -> dict:
    return FlowDefinitionResponse.model_validate(definition).model_dump()


def _instance_to_response(instance) -> dict:
    return FlowInstanceResponse.model_validate(instance).model_dump()


@router.get("/flows/definitions")
def list_flow_definitions(
    params: PaginationParams = Depends(),
    session: Session = Depends(get_db),
):
    result = flow_service.list_definitions(session, params)
    result["items"] = [_definition_to_response(d) for d in result["items"]]
    return result


@router.post("/flows/definitions", response_model=FlowDefinitionResponse, status_code=201)
def create_flow_definition(
    data: FlowDefinitionCreate,
    session: Session = Depends(get_db),
):
    payload = data.model_dump()
    payload["steps"] = [s.model_dump() for s in data.steps]
    definition = flow_service.create_definition(session, payload)
    session.commit()
    return definition


@router.get("/flows/definitions/{definition_id}", response_model=FlowDefinitionResponse)
def get_flow_definition(
    definition_id: int,
    session: Session = Depends(get_db),
):
    return flow_service.get_definition(session, definition_id)


@router.put("/flows/definitions/{definition_id}", response_model=FlowDefinitionResponse)
def update_flow_definition(
    definition_id: int,
    data: FlowDefinitionUpdate,
    session: Session = Depends(get_db),
):
    update_data = data.model_dump(exclude_unset=True)
    if "steps" in update_data and update_data["steps"] is not None:
        update_data["steps"] = [
            s.model_dump() if hasattr(s, "model_dump") else s for s in update_data["steps"]
        ]
    definition = flow_service.update_definition(session, definition_id, update_data)
    session.commit()
    return definition


@router.get("/flows/instances")
def list_flow_instances(
    params: PaginationParams = Depends(),
    status: str | None = Query(None),
    flow_definition_id: int | None = Query(None),
    session: Session = Depends(get_db),
):
    result = flow_service.list_instances(
        session,
        params,
        status=status,
        flow_definition_id=flow_definition_id,
    )
    result["items"] = [_instance_to_response(i) for i in result["items"]]
    return result


@router.post("/flows/instances", response_model=FlowInstanceResponse, status_code=201)
def create_flow_instance(
    data: FlowInstanceCreate,
    session: Session = Depends(get_db),
):
    instance = flow_service.create_instance(session, data.flow_definition_id, data.context)
    session.commit()
    return instance


@router.post("/flows/instances/{instance_id}/advance", status_code=202)
def advance_flow_instance(
    instance_id: int,
    session: Session = Depends(get_db),
):
    result = flow_service.advance_flow(instance_id, session)
    session.commit()
    return result


@router.get("/flows/instances/{instance_id}", response_model=FlowInstanceResponse)
def get_flow_instance(
    instance_id: int,
    session: Session = Depends(get_db),
):
    return flow_service.get_instance(session, instance_id)


@router.post("/flows/instances/{instance_id}/retry", status_code=202)
def retry_flow_instance(
    instance_id: int,
    session: Session = Depends(get_db),
):
    instance = flow_service.retry_instance(session, instance_id)
    session.commit()
    return {
        "status": "accepted",
        "instance_id": instance.id,
        "message": "Instance retry queued",
    }


@router.post("/flows/instances/{instance_id}/cancel")
def cancel_flow_instance(
    instance_id: int,
    session: Session = Depends(get_db),
):
    instance = flow_service.cancel_instance(session, instance_id)
    session.commit()
    return {"status": "cancelled", "instance_id": instance.id}
