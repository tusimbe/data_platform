from sqlalchemy import Integer, String
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin

JSONType = SQLiteJSON


class FieldMapping(Base, TimestampMixin):
    __tablename__ = "field_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(100), nullable=False)
    target_table: Mapped[str] = mapped_column(String(100), nullable=False)
    source_field: Mapped[str] = mapped_column(String(100), nullable=False)
    target_field: Mapped[str] = mapped_column(String(100), nullable=False)
    transform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    transform_config: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class EntitySchema(Base, TimestampMixin):
    __tablename__ = "entity_schemas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_data: Mapped[dict] = mapped_column(JSONType, nullable=False)
