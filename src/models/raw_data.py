from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

JSONType = SQLiteJSON


class RawData(Base):
    __tablename__ = "raw_data"
    __table_args__ = (
        UniqueConstraint("connector_id", "entity", "external_id", name="uq_raw_data_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sync_log_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sync_logs.id"), nullable=True
    )
