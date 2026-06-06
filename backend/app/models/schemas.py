from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    resend_domain: str | None
    created_at: datetime


class LogoutResponse(BaseModel):
    logged_out: bool = True


class UpdateMeRequest(BaseModel):
    resend_domain: str | None = Field(default=None, max_length=253)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    url: str = Field(max_length=2048)

    @field_validator("url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class IngestResponse(BaseModel):
    job_id: uuid.UUID


class IngestionResultResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    current_step: str | None
    profile: dict | None
    error_message: str | None


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    product_name: str
    one_liner: str | None
    target_customer: str | None
    pain_points: list[str]
    differentiators: list[str]
    case_studies: list[str]
    cta: str | None
    icp: str | None
    avoid_messaging: str | None
    source_url: str | None
    updated_at: datetime | None


class SaveProfileRequest(BaseModel):
    product_name: str = Field(max_length=200)
    one_liner: str | None = Field(default=None, max_length=500)
    target_customer: str | None = Field(default=None, max_length=500)
    pain_points: list[str] = Field(default_factory=list, max_length=20)
    differentiators: list[str] = Field(default_factory=list, max_length=20)
    case_studies: list[str] = Field(default_factory=list, max_length=20)
    cta: str | None = Field(default=None, max_length=300)
    icp: str | None = Field(default=None, max_length=500)
    avoid_messaging: str | None = Field(default=None, max_length=1000)
    source_url: str | None = None


class SaveProfileResponse(BaseModel):
    profile_id: uuid.UUID


class UpdateProfileRequest(BaseModel):
    product_name: str | None = Field(default=None, max_length=200)
    one_liner: str | None = Field(default=None, max_length=500)
    target_customer: str | None = Field(default=None, max_length=500)
    pain_points: list[str] | None = None
    differentiators: list[str] | None = None
    case_studies: list[str] | None = None
    cta: str | None = Field(default=None, max_length=300)
    icp: str | None = Field(default=None, max_length=500)
    avoid_messaging: str | None = Field(default=None, max_length=1000)


class UpdateProfileResponse(BaseModel):
    profile_id: uuid.UUID
    updated_at: datetime


# ---------------------------------------------------------------------------
# Outreach
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    company_name: str = Field(max_length=100, pattern=r"^[a-zA-Z0-9 \-]+$")
    contact_name: str | None = Field(default=None, max_length=100)


class GenerateResponse(BaseModel):
    job_id: uuid.UUID


class OutreachStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    current_step: str | None
    created_at: datetime


class OutreachResultResponse(BaseModel):
    id: uuid.UUID
    company_name: str
    contact_name: str | None
    status: str
    send_status: str
    data_confidence: str | None
    email_subject: str | None
    email_draft: str | None
    linkedin_draft: str | None
    schedule_json: dict | None
    error_message: str | None
    token_usage: int | None
    created_at: datetime
    completed_at: datetime | None


class EditDraftRequest(BaseModel):
    email_subject: str | None = Field(default=None, max_length=500)
    email_draft: str | None = Field(default=None, max_length=10000)
    linkedin_draft: str | None = Field(default=None, max_length=300)


class EditDraftResponse(BaseModel):
    updated: bool = True
    updated_at: datetime


class SendRequest(BaseModel):
    to_email: EmailStr


class SendResponse(BaseModel):
    sent: bool = True
    resend_message_id: str
    sent_at: datetime


class RetryResponse(BaseModel):
    job_id: uuid.UUID
    retry_count: int


class HistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_name: str
    contact_name: str | None
    status: str
    send_status: str
    data_confidence: str | None
    token_usage: int | None
    created_at: datetime
    sent_at: datetime | None


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    total: int
    page: int
    per_page: int


class DeleteJobResponse(BaseModel):
    deleted: bool = True


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


class BatchCreateResponse(BaseModel):
    batch_id: uuid.UUID
    total: int


class BatchProspectStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    company_name: str
    contact_name: str | None
    status: str
    current_step: str | None
    send_status: str
    data_confidence: str | None


class BatchStatusResponse(BaseModel):
    batch_id: uuid.UUID
    status: str
    total: int
    research_done: int
    personalize_done: int
    prospects: list[BatchProspectStatus]
    created_at: datetime
    completed_at: datetime | None


# ---------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------


class CRMRecord(BaseModel):
    company_name: str
    contact_name: str | None
    stage: str
    last_contacted: str


class CRMPipelineResponse(BaseModel):
    records: list[CRMRecord]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    error: str
    code: str
