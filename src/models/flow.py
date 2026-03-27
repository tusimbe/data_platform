from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

JSONType = SQLiteJSON


class FlowDefinition(Base, TimestampMixin):
    __tablename__ = "flow_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[dict] = mapped_column(JSONType, nullable=False)

    instances = relationship("FlowInstance", back_populates="flow_definition")


class FlowInstance(Base, TimestampMixin):
    __tablename__ = "flow_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flow_definition_id: Mapped[int] = mapped_column(
        ForeignKey("flow_definitions.id"), nullable=False
    )
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    context: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    flow_definition = relationship("FlowDefinition", back_populates="instances")
