# src/api/routes/field_mappings.py
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key, PaginationParams
from src.api.schemas.field_mapping import FieldMappingCreate, FieldMappingUpdate
from src.services import field_mapping_crud_service as svc

router = APIRouter(dependencies=[Depends(get_current_api_key)])


@router.get("/field-mappings")
def list_field_mappings(
    params: PaginationParams = Depends(),
    connector_type: str | None = Query(None),
    source_entity: str | None = Query(None),
    session: Session = Depends(get_db),
):
    result = svc.list_field_mappings(session, params, connector_type, source_entity)
    result["items"] = [svc.field_mapping_to_response(m) for m in result["items"]]
    return result


@router.post("/field-mappings", status_code=201)
def create_field_mapping(
    data: FieldMappingCreate,
    session: Session = Depends(get_db),
):
    mapping = svc.create_field_mapping(session, data.model_dump())
    session.commit()
    return svc.field_mapping_to_response(mapping)


@router.get("/field-mappings/{mapping_id}")
def get_field_mapping(
    mapping_id: int,
    session: Session = Depends(get_db),
):
    mapping = svc.get_field_mapping(session, mapping_id)
    return svc.field_mapping_to_response(mapping)


@router.put("/field-mappings/{mapping_id}")
def update_field_mapping(
    mapping_id: int,
    data: FieldMappingUpdate,
    session: Session = Depends(get_db),
):
    mapping = svc.update_field_mapping(session, mapping_id, data.model_dump(exclude_unset=True))
    session.commit()
    return svc.field_mapping_to_response(mapping)


@router.delete("/field-mappings/{mapping_id}", status_code=204)
def delete_field_mapping(
    mapping_id: int,
    session: Session = Depends(get_db),
):
    svc.delete_field_mapping(session, mapping_id)
    session.commit()
    return Response(status_code=204)
