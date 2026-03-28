# src/api/schemas/field_mapping.py
"""字段映射 + 实体 Schema 的请求/响应模型"""

from datetime import datetime
from pydantic import BaseModel, Field


# ─── FieldMapping ───────────────────────────────────────────────

VALID_TRANSFORMS = ("date_format", "value_map", "concat", "split")


class FieldMappingCreate(BaseModel):
    connector_type: str = Field(..., min_length=1, max_length=50)
    source_entity: str = Field(..., min_length=1, max_length=100)
    target_table: str = Field(..., min_length=1, max_length=100)
    source_field: str = Field(..., min_length=1, max_length=100)
    target_field: str = Field(..., min_length=1, max_length=100)
    transform: str | None = Field(None, max_length=50)
    transform_config: dict | None = None


class FieldMappingUpdate(BaseModel):
    connector_type: str | None = Field(None, min_length=1, max_length=50)
    source_entity: str | None = Field(None, min_length=1, max_length=100)
    target_table: str | None = Field(None, min_length=1, max_length=100)
    source_field: str | None = Field(None, min_length=1, max_length=100)
    target_field: str | None = Field(None, min_length=1, max_length=100)
    transform: str | None = Field(None, max_length=50)
    transform_config: dict | None = None


class FieldMappingResponse(BaseModel):
    id: int
    connector_type: str
    source_entity: str
    target_table: str
    source_field: str
    target_field: str
    transform: str | None
    transform_config: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── EntitySchema ───────────────────────────────────────────────


class EntitySchemaCreate(BaseModel):
    connector_type: str = Field(..., min_length=1, max_length=50)
    entity: str = Field(..., min_length=1, max_length=100)
    schema_data: dict = Field(...)


class EntitySchemaUpdate(BaseModel):
    connector_type: str | None = Field(None, min_length=1, max_length=50)
    entity: str | None = Field(None, min_length=1, max_length=100)
    schema_data: dict | None = None


class EntitySchemaResponse(BaseModel):
    id: int
    connector_type: str
    entity: str
    schema_data: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
