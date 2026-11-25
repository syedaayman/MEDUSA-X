"""Patient summary API routes."""

from fastapi import APIRouter

from models.response import SummaryResponse

router = APIRouter(prefix="/api/patient", tags=["reports"])


@router.get("/{patient_id}/summary", response_model=SummaryResponse)
def get_patient_summary(patient_id: str) -> SummaryResponse:
    """Return an explicitly unavailable summary until evidence is processed."""
    return SummaryResponse(patient_id=patient_id)
