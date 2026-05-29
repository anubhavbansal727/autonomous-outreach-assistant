"""Unit tests for Pydantic v2 request/response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


class TestRegisterRequest:
    def test_valid(self):
        from app.models.schemas import RegisterRequest
        req = RegisterRequest(email="user@example.com", password="password123")
        assert req.email == "user@example.com"

    def test_invalid_email(self):
        from app.models.schemas import RegisterRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", password="password123")

    def test_password_too_short(self):
        from app.models.schemas import RegisterRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@example.com", password="short")


class TestIngestRequest:
    def test_valid_https(self):
        from app.models.schemas import IngestRequest
        req = IngestRequest(url="https://example.com")
        assert req.url == "https://example.com"

    def test_valid_http(self):
        from app.models.schemas import IngestRequest
        req = IngestRequest(url="http://example.com")
        assert req.url == "http://example.com"

    def test_no_scheme_raises(self):
        from app.models.schemas import IngestRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="http"):
            IngestRequest(url="example.com/no-scheme")

    def test_ftp_raises(self):
        from app.models.schemas import IngestRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            IngestRequest(url="ftp://example.com")


class TestGenerateRequest:
    def test_valid(self):
        from app.models.schemas import GenerateRequest
        req = GenerateRequest(company_name="Acme Corp", contact_name="Jane Doe")
        assert req.company_name == "Acme Corp"

    def test_contact_name_optional(self):
        from app.models.schemas import GenerateRequest
        req = GenerateRequest(company_name="Acme Corp")
        assert req.contact_name is None

    def test_special_chars_in_name_raise(self):
        from app.models.schemas import GenerateRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            GenerateRequest(company_name="Acme <Corp>")

    def test_name_too_long_raises(self):
        from app.models.schemas import GenerateRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            GenerateRequest(company_name="A" * 101)


class TestSendRequest:
    def test_valid_email(self):
        from app.models.schemas import SendRequest
        req = SendRequest(to_email="prospect@company.com")
        assert str(req.to_email) == "prospect@company.com"

    def test_invalid_email_raises(self):
        from app.models.schemas import SendRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SendRequest(to_email="not-an-email")


class TestHistoryItem:
    def test_from_orm_attributes(self):
        from app.models.schemas import HistoryItem
        now = datetime.now(timezone.utc)
        item = HistoryItem.model_validate({
            "id": uuid.uuid4(),
            "company_name": "Test Co",
            "contact_name": None,
            "status": "done",
            "send_status": "draft",
            "data_confidence": "high",
            "token_usage": None,
            "created_at": now,
            "sent_at": None,
        })
        assert item.company_name == "Test Co"
        assert item.status == "done"


class TestEditDraftRequest:
    def test_all_fields_optional(self):
        from app.models.schemas import EditDraftRequest
        req = EditDraftRequest()
        assert req.email_subject is None
        assert req.email_draft is None
        assert req.linkedin_draft is None

    def test_linkedin_draft_max_length(self):
        from app.models.schemas import EditDraftRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            EditDraftRequest(linkedin_draft="x" * 301)
