"""Patient and timeline API routes."""

from fastapi import APIRouter

from models.clinical_event import TimelineResponse
from models.conflict import ConflictResponse
from models.patient import PatientResponse

router = APIRouter(prefix="/api/patient", tags=["patients"])


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(patient_id: str) -> PatientResponse:
    """Return an empty patient record until a real data source is connected."""
    return PatientResponse(patient_id=patient_id)


@router.get("/{patient_id}/timeline", response_model=TimelineResponse)
def get_patient_timeline(patient_id: str) -> TimelineResponse:
    """Return an empty timeline rather than inventing clinical events."""
    return TimelineResponse(patient_id=patient_id, events=[])


@router.get("/{patient_id}/conflicts", response_model=ConflictResponse)
def get_patient_conflicts(patient_id: str) -> ConflictResponse:
    """Return no conflicts until document reconciliation is implemented."""
    return ConflictResponse(patient_id=patient_id, conflicts=[])
