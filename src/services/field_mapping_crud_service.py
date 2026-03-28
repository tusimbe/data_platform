# src/services/field_mapping_crud_service.py
from sqlalchemy.orm import Session

from src.api.deps import PaginationParams, paginate
from src.core.exceptions import NotFoundError, ConflictError, ValidationError
from src.models.field_mapping import FieldMapping, EntitySchema

VALID_TRANSFORMS = {"date_format", "value_map", "concat", "split"}


# ─── FieldMapping CRUD ──────────────────────────────────────────


def list_field_mappings(
    session: Session,
    params: PaginationParams,
    connector_type: str | None = None,
    source_entity: str | None = None,
) -> dict:
    query = session.query(FieldMapping).order_by(FieldMapping.id)
    if connector_type:
        query = query.filter(FieldMapping.connector_type == connector_type)
    if source_entity:
        query = query.filter(FieldMapping.source_entity == source_entity)
    return paginate(query, params)


def get_field_mapping(session: Session, mapping_id: int) -> FieldMapping:
    mapping = session.query(FieldMapping).filter_by(id=mapping_id).first()
    if not mapping:
        raise NotFoundError(f"FieldMapping with id {mapping_id} not found")
    return mapping


def create_field_mapping(session: Session, data: dict) -> FieldMapping:
    transform = data.get("transform")
    if transform and transform not in VALID_TRANSFORMS:
        raise ValidationError(f"Invalid transform: {transform}. Valid: {sorted(VALID_TRANSFORMS)}")

    # Check for duplicate (same connector_type + source_entity + source_field + target_field)
    existing = (
        session.query(FieldMapping)
        .filter_by(
            connector_type=data["connector_type"],
            source_entity=data["source_entity"],
            source_field=data["source_field"],
            target_field=data["target_field"],
        )
        .first()
    )
    if existing:
        raise ConflictError(
            f"Mapping already exists: {data['source_field']} -> {data['target_field']} "
            f"for {data['connector_type']}/{data['source_entity']}"
        )

    mapping = FieldMapping(**data)
    session.add(mapping)
    session.flush()
    return mapping


def update_field_mapping(session: Session, mapping_id: int, data: dict) -> FieldMapping:
    mapping = get_field_mapping(session, mapping_id)

    transform = data.get("transform")
    if transform and transform not in VALID_TRANSFORMS:
        raise ValidationError(f"Invalid transform: {transform}. Valid: {sorted(VALID_TRANSFORMS)}")

    for key, value in data.items():
        if value is None:
            continue
        if hasattr(mapping, key):
            setattr(mapping, key, value)

    session.flush()
    return mapping


def delete_field_mapping(session: Session, mapping_id: int) -> None:
    mapping = get_field_mapping(session, mapping_id)
    session.delete(mapping)
    session.flush()


def field_mapping_to_response(mapping: FieldMapping) -> dict:
    return {
        "id": mapping.id,
        "connector_type": mapping.connector_type,
        "source_entity": mapping.source_entity,
        "target_table": mapping.target_table,
        "source_field": mapping.source_field,
        "target_field": mapping.target_field,
        "transform": mapping.transform,
        "transform_config": mapping.transform_config,
        "created_at": mapping.created_at,
        "updated_at": mapping.updated_at,
    }


def get_mappings_for_sync(session: Session, connector_type: str, source_entity: str) -> list[dict]:
    """Query field_mappings table for a specific connector+entity pair.
    Returns list of dicts compatible with FieldMappingService.apply_mappings()."""
    mappings = (
        session.query(FieldMapping)
        .filter_by(connector_type=connector_type, source_entity=source_entity)
        .all()
    )
    return [
        {
            "source_field": m.source_field,
            "target_field": m.target_field,
            "transform": m.transform,
            "transform_config": m.transform_config or {},
        }
        for m in mappings
    ]


# ─── EntitySchema CRUD ──────────────────────────────────────────


def list_entity_schemas(
    session: Session,
    params: PaginationParams,
    connector_type: str | None = None,
    entity: str | None = None,
) -> dict:
    query = session.query(EntitySchema).order_by(EntitySchema.id)
    if connector_type:
        query = query.filter(EntitySchema.connector_type == connector_type)
    if entity:
        query = query.filter(EntitySchema.entity == entity)
    return paginate(query, params)


def get_entity_schema(session: Session, schema_id: int) -> EntitySchema:
    schema = session.query(EntitySchema).filter_by(id=schema_id).first()
    if not schema:
        raise NotFoundError(f"EntitySchema with id {schema_id} not found")
    return schema


def create_entity_schema(session: Session, data: dict) -> EntitySchema:
    # Upsert semantics: if same connector_type + entity exists, update it
    existing = (
        session.query(EntitySchema)
        .filter_by(
            connector_type=data["connector_type"],
            entity=data["entity"],
        )
        .first()
    )
    if existing:
        existing.schema_data = data["schema_data"]
        session.flush()
        return existing

    schema = EntitySchema(**data)
    session.add(schema)
    session.flush()
    return schema


def update_entity_schema(session: Session, schema_id: int, data: dict) -> EntitySchema:
    schema = get_entity_schema(session, schema_id)
    for key, value in data.items():
        if value is None:
            continue
        if hasattr(schema, key):
            setattr(schema, key, value)
    session.flush()
    return schema


def delete_entity_schema(session: Session, schema_id: int) -> None:
    schema = get_entity_schema(session, schema_id)
    session.delete(schema)
    session.flush()


def entity_schema_to_response(schema: EntitySchema) -> dict:
    return {
        "id": schema.id,
        "connector_type": schema.connector_type,
        "entity": schema.entity,
        "schema_data": schema.schema_data,
        "created_at": schema.created_at,
        "updated_at": schema.updated_at,
    }
