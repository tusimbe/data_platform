# src/api/routes/entity_schemas.py
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from src.api.deps import get_db, get_current_api_key, PaginationParams
from src.api.schemas.field_mapping import EntitySchemaCreate, EntitySchemaUpdate
from src.services import field_mapping_crud_service as svc

router = APIRouter(dependencies=[Depends(get_current_api_key)])


@router.get("/entity-schemas")
def list_entity_schemas(
    params: PaginationParams = Depends(),
    connector_type: str | None = Query(None),
    entity: str | None = Query(None),
    session: Session = Depends(get_db),
):
    result = svc.list_entity_schemas(session, params, connector_type, entity)
    result["items"] = [svc.entity_schema_to_response(s) for s in result["items"]]
    return result


@router.post("/entity-schemas", status_code=201)
def create_entity_schema(
    data: EntitySchemaCreate,
    session: Session = Depends(get_db),
):
    schema = svc.create_entity_schema(session, data.model_dump())
    session.commit()
    return svc.entity_schema_to_response(schema)


@router.get("/entity-schemas/{schema_id}")
def get_entity_schema(
    schema_id: int,
    session: Session = Depends(get_db),
):
    schema = svc.get_entity_schema(session, schema_id)
    return svc.entity_schema_to_response(schema)


@router.put("/entity-schemas/{schema_id}")
def update_entity_schema(
    schema_id: int,
    data: EntitySchemaUpdate,
    session: Session = Depends(get_db),
):
    schema = svc.update_entity_schema(session, schema_id, data.model_dump(exclude_unset=True))
    session.commit()
    return svc.entity_schema_to_response(schema)


@router.delete("/entity-schemas/{schema_id}", status_code=204)
def delete_entity_schema(
    schema_id: int,
    session: Session = Depends(get_db),
):
    svc.delete_entity_schema(session, schema_id)
    session.commit()
    return Response(status_code=204)
