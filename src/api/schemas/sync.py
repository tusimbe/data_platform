# src/api/schemas/sync.py
from datetime import datetime

from pydantic import BaseModel, Field


class SyncTaskCreate(BaseModel):
    connector_id: int
    entity: str = Field(..., min_length=1, max_length=100)
    direction: str = Field(..., pattern="^(pull|push)$")
    cron_expression: str | None = Field(None, max_length=100)
    enabled: bool = True


class SyncTaskUpdate(BaseModel):
    entity: str | None = Field(None, min_length=1, max_length=100)
    direction: str | None = Field(None, pattern="^(pull|push)$")
    cron_expression: str | None = None
    enabled: bool | None = None


class SyncTaskResponse(BaseModel):
    id: int
    connector_id: int
    entity: str
    direction: str
    cron_expression: str | None
    enabled: bool
    last_sync_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SyncLogResponse(BaseModel):
    id: int
    sync_task_id: int | None
    connector_id: int
    entity: str
    direction: str
    status: str
    total_records: int
    success_count: int
    failure_count: int
    error_details: dict | None
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class SyncTaskTriggerResponse(BaseModel):
    status: str
    task_id: int
    celery_task_id: str
    message: str
