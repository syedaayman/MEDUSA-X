"""Clinical timeline response models."""

from pydantic import BaseModel


class ClinicalEvent(BaseModel):
    """Evidence-linked timeline item."""

    event_id: str
    occurred_at: str | None = None
    description: str
    document_id: str
    page_number: int


class TimelineResponse(BaseModel):
    """Patient timeline response."""

    patient_id: str
    data_status: str = "no_records"
    events: list[ClinicalEvent]
