"""Document ingestion response models."""

from pydantic import BaseModel


class ExtractedPage(BaseModel):
    """Selectable text extracted from one source page."""

    page_number: int
    text: str


class PDFExtractionResult(BaseModel):
    """PDF extraction results and pages requiring OCR."""

    page_count: int
    pages: list[ExtractedPage]
    ocr_required_pages: list[int]


class UploadResponse(PDFExtractionResult):
    """Upload endpoint response."""

    filename: str
    status: str
    message: str
