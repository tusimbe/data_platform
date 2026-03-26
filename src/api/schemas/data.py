# src/api/schemas/data.py
from pydantic import BaseModel, Field


class PushRequest(BaseModel):
    records: list[dict] = Field(..., min_length=1)


class PushResponse(BaseModel):
    success_count: int
    failure_count: int
    failures: list[dict] = Field(default_factory=list)
