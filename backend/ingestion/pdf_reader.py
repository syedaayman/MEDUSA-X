"""PDF text extraction using PyMuPDF."""

import pymupdf

from models.document import ExtractedPage, PDFExtractionResult


def extract_pdf_text(pdf_bytes: bytes) -> PDFExtractionResult:
    """Extract selectable text from each page of a PDF byte stream."""
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
            pages = [
                ExtractedPage(page_number=number, text=page.get_text("text").strip())
                for number, page in enumerate(document, start=1)
            ]
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise ValueError("The uploaded file could not be read as a valid PDF.") from exc

    return PDFExtractionResult(
        page_count=len(pages),
        pages=pages,
        ocr_required_pages=[page.page_number for page in pages if not page.text],
    )
