"""Clinical conflict response models."""

from pydantic import BaseModel


class Conflict(BaseModel):
    """Evidence-linked discrepancy."""

    conflict_id: str
    category: str
    description: str
    document_ids: list[str]


class ConflictResponse(BaseModel):
    """Patient conflict response."""

    patient_id: str
    data_status: str = "no_records"
    conflicts: list[Conflict]
