"""Patient response models."""

from pydantic import BaseModel


class PatientResponse(BaseModel):
    """Patient record availability response."""

    patient_id: str
    display_name: str | None = None
    data_status: str = "no_records"
    clinical_data_available: bool = False
