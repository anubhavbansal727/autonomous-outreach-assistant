# backend/app/models/schemas.py
# Pydantic v2 request/response schemas — populated in Week 3
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
