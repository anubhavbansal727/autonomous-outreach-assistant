from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.models.db import User
from app.models.schemas import CRMPipelineResponse, CRMRecord

router = APIRouter(prefix="/crm", tags=["crm"])

_MOCK_PIPELINE = [
    CRMRecord(
        company_name="Acme Corp",
        contact_name="Jane Smith",
        stage="negotiating",
        last_contacted="2026-05-10",
    ),
    CRMRecord(
        company_name="GlobalTech Inc",
        contact_name="Bob Lee",
        stage="demo_booked",
        last_contacted="2026-05-20",
    ),
    CRMRecord(
        company_name="Nexus Payments",
        contact_name=None,
        stage="closed_won",
        last_contacted="2026-04-15",
    ),
    CRMRecord(
        company_name="Vortex Labs",
        contact_name="Sarah Kim",
        stage="exploring",
        last_contacted="2026-05-01",
    ),
    CRMRecord(
        company_name="Prism Analytics",
        contact_name="Mike Chen",
        stage="closed_lost",
        last_contacted="2026-05-25",
    ),
]


@router.get("/pipeline", response_model=CRMPipelineResponse)
async def get_pipeline(
    current_user: User = Depends(get_current_user),
) -> CRMPipelineResponse:
    return CRMPipelineResponse(records=_MOCK_PIPELINE)
