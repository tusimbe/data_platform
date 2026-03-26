from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

# Use JSON type that works with both SQLite (testing) and PostgreSQL (production)
# SQLAlchemy handles the dialect-specific type mapping
JSONType = SQLiteJSON


class Connector(Base, TimestampMixin):
    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    auth_config: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    sync_tasks = relationship("SyncTask", back_populates="connector")
    sync_logs = relationship("SyncLog", back_populates="connector")
