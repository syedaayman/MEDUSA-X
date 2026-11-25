"""Document upload API routes."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from ingestion.pdf_reader import extract_pdf_text
from models.document import UploadResponse

router = APIRouter(prefix="/api", tags=["documents"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    """Extract selectable text from an uploaded PDF without persisting the file."""
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF documents are supported.")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF uploads must be 20 MB or smaller.")
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")

    try:
        extraction = extract_pdf_text(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return UploadResponse(
        filename=filename,
        status="text_extracted",
        message=(
            "Text extraction completed. Scanned pages are not OCR-processed; "
            "no clinical findings have been generated."
        ),
        page_count=extraction.page_count,
        pages=extraction.pages,
        ocr_required_pages=extraction.ocr_required_pages,
    )
