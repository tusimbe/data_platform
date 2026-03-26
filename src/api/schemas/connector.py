# src/api/schemas/connector.py
from datetime import datetime

from pydantic import BaseModel, Field


class ConnectorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    connector_type: str = Field(..., min_length=1, max_length=50)
    base_url: str = Field(..., min_length=1, max_length=500)
    auth_config: dict = Field(default_factory=dict)
    description: str | None = None


class ConnectorUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    connector_type: str | None = Field(None, min_length=1, max_length=50)
    base_url: str | None = Field(None, min_length=1, max_length=500)
    auth_config: dict | None = None
    description: str | None = None
    enabled: bool | None = None


class ConnectorResponse(BaseModel):
    id: int
    name: str
    connector_type: str
    base_url: str
    has_auth_config: bool
    enabled: bool
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
