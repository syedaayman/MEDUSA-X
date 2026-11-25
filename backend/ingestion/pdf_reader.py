"""PDF text extraction.

PyMuPDF is used when available. A dependency-free stdlib fallback keeps the
pipeline usable (and testable) when PyMuPDF is not installed; it only reads
simple text-bearing PDFs and never pretends scanned pages were extracted.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field

try:  # pragma: no cover - exercised only when PyMuPDF is present
    import pymupdf  # type: ignore
except Exception:  # noqa: BLE001 - optional dependency
    pymupdf = None

MIN_PAGE_CHARS = 40


@dataclass
class ExtractedPage:
    page_number: int
    text: str = ""
    ocr_required: bool = False


@dataclass
class PDFExtractionResult:
    pages: list[ExtractedPage] = field(default_factory=list)
    page_count: int = 0
    extraction_quality: float = 0.0
    ocr_required_pages: list[int] = field(default_factory=list)
    engine: str = "stdlib"
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.page_count > 0


def looks_like_pdf(pdf_bytes: bytes) -> bool:
    """Cheap structural check before attempting extraction."""
    if not pdf_bytes or len(pdf_bytes) < 64:
        return False
    return b"%PDF-" in pdf_bytes[:1024]


def _quality(pages: list[ExtractedPage]) -> float:
    if not pages:
        return 0.0
    readable = sum(1 for page in pages if len(page.text.strip()) >= MIN_PAGE_CHARS)
    return round(readable / len(pages), 3)


def extract_pdf_text(pdf_bytes: bytes) -> PDFExtractionResult:
    """Extract selectable text per page, marking pages that need OCR."""
    if not looks_like_pdf(pdf_bytes):
        return PDFExtractionResult(error="NOT_A_PDF")

    if pymupdf is not None:
        result = _extract_with_pymupdf(pdf_bytes)
        if result.ok and result.extraction_quality > 0:
            return result
        fallback = _extract_with_stdlib(pdf_bytes)
        if fallback.ok and fallback.extraction_quality >= result.extraction_quality:
            return fallback
        return result

    return _extract_with_stdlib(pdf_bytes)


def _extract_with_pymupdf(pdf_bytes: bytes) -> PDFExtractionResult:
    pages: list[ExtractedPage] = []
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:  # type: ignore[union-attr]
            for index, page in enumerate(document, start=1):
                text = (page.get_text() or "").strip()
                pages.append(ExtractedPage(page_number=index, text=text, ocr_required=len(text) < MIN_PAGE_CHARS))
    except Exception as exc:  # noqa: BLE001 - malformed PDFs are expected input
        return PDFExtractionResult(error=f"PDF_READ_ERROR: {exc}", engine="pymupdf")

    ocr_pages = [page.page_number for page in pages if page.ocr_required]
    return PDFExtractionResult(
        pages=pages,
        page_count=len(pages),
        extraction_quality=_quality(pages),
        ocr_required_pages=ocr_pages,
        engine="pymupdf",
    )


_STREAM_RE = re.compile(rb"stream\r?\n(.*?)endstream", re.S)
_TEXT_BLOCK_RE = re.compile(rb"BT(.*?)ET", re.S)
_STRING_RE = re.compile(rb"\((?:\\.|[^\\()])*\)", re.S)


def _decode_pdf_string(raw: bytes) -> str:
    body = raw[1:-1]
    out = bytearray()
    index = 0
    while index < len(body):
        char = body[index]
        if char == 0x5C and index + 1 < len(body):  # backslash escape
            nxt = body[index + 1 : index + 2]
            mapping = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}
            if nxt in mapping:
                out += mapping[nxt]
                index += 2
                continue
            if nxt.isdigit():
                octal = body[index + 1 : index + 4]
                digits = re.match(rb"[0-7]{1,3}", octal)
                if digits:
                    out.append(int(digits.group(0), 8) & 0xFF)
                    index += 1 + len(digits.group(0))
                    continue
            out += nxt
            index += 2
            continue
        out.append(char)
        index += 1
    return out.decode("latin-1", errors="replace")


def _extract_with_stdlib(pdf_bytes: bytes) -> PDFExtractionResult:
    """Best-effort extraction of text operators from uncompressed streams."""
    pages: list[ExtractedPage] = []
    try:
        for raw in _STREAM_RE.findall(pdf_bytes):
            payload = raw
            if not _TEXT_BLOCK_RE.search(payload):
                try:
                    payload = zlib.decompress(raw)
                except zlib.error:
                    try:
                        payload = zlib.decompressobj().decompress(raw)
                    except zlib.error:
                        continue
            blocks = _TEXT_BLOCK_RE.findall(payload)
            if not blocks:
                continue
            lines: list[str] = []
            for block in blocks:
                for chunk in re.split(rb"T\*|Td|TD|'", block):
                    text = "".join(_decode_pdf_string(s) for s in _STRING_RE.findall(chunk))
                    text = text.strip()
                    if text:
                        lines.append(text)
            if lines:
                content = "\n".join(lines).strip()
                pages.append(
                    ExtractedPage(
                        page_number=len(pages) + 1,
                        text=content,
                        ocr_required=len(content) < MIN_PAGE_CHARS,
                    )
                )
    except Exception as exc:  # noqa: BLE001
        return PDFExtractionResult(error=f"PDF_READ_ERROR: {exc}", engine="stdlib")

    if not pages:
        return PDFExtractionResult(
            error="NO_EXTRACTABLE_TEXT",
            engine="stdlib",
            page_count=0,
            extraction_quality=0.0,
        )

    ocr_pages = [page.page_number for page in pages if page.ocr_required]
    return PDFExtractionResult(
        pages=pages,
        page_count=len(pages),
        extraction_quality=_quality(pages),
        ocr_required_pages=ocr_pages,
        engine="stdlib",
    )
