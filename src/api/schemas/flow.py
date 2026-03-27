from datetime import datetime

from pydantic import BaseModel, Field


class FlowStepSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    action: str = Field(..., min_length=1, max_length=100)
    timeout_minutes: int | None = Field(None, ge=1)


class FlowDefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    steps: list[FlowStepSchema] = Field(..., min_length=1)


class FlowDefinitionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    steps: list[FlowStepSchema] | None = Field(None, min_length=1)


class FlowDefinitionResponse(BaseModel):
    id: int
    name: str
    description: str | None
    steps: list[dict]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FlowInstanceResponse(BaseModel):
    id: int
    flow_definition_id: int
    current_step: int
    status: str
    context: dict
    error_message: str | None
    retry_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
