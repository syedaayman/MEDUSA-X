"""Clinical summary response models."""

from pydantic import BaseModel, Field


class SummaryResponse(BaseModel):
    """Summary availability response."""

    patient_id: str
    data_status: str = "no_records"
    summary: str | None = None
    uncertainty_notes: list[str] = Field(default_factory=list)
