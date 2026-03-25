from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, ForeignKey, func
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

JSONType = SQLiteJSON


class SyncTask(Base, TimestampMixin):
    __tablename__ = "sync_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "pull" | "push"
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    connector = relationship("Connector", back_populates="sync_tasks")
    sync_logs = relationship("SyncLog", back_populates="sync_task")


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_task_id: Mapped[int | None] = mapped_column(ForeignKey("sync_tasks.id"), nullable=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    error_details: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sync_task = relationship("SyncTask", back_populates="sync_logs")
    connector = relationship("Connector", back_populates="sync_logs")
