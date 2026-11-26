"""Minimal PDF writer used for controlled fixtures and the local demo seed.

Produces a valid single-font PDF with one text stream per page. This keeps the
demo and test suite runnable without any third-party document library.
"""

from __future__ import annotations

import zlib


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content_stream(lines: list[str]) -> bytes:
    ops = ["BT", "/F1 11 Tf", "15 TL", "40 800 Td"]
    for line in lines:
        ops.append(f"({_escape(line[:110])}) Tj")
        ops.append("T*")
    ops.append("ET")
    return "\n".join(ops).encode("latin-1", errors="replace")


def build_pdf(pages: list[str], compress: bool = False) -> bytes:
    """Build a PDF byte string containing the supplied page texts."""
    page_ids: list[int] = []
    content_ids: dict[int, int] = {}
    next_id = 4
    for _ in range(len(pages)):
        page_ids.append(next_id)
        content_ids[next_id] = next_id + 1
        next_id += 2

    objects: dict[int, bytes] = {}
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for index, page_id in enumerate(page_ids):
        lines = pages[index].split("\n")
        stream = _content_stream(lines)
        if compress:
            stream = zlib.compress(stream)
            filter_op = b" /Filter /FlateDecode"
        else:
            filter_op = b""
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_ids[page_id]} 0 R >>"
        ).encode()
        objects[content_ids[page_id]] = (
            b"<< /Length " + str(len(stream)).encode() + filter_op + b" >>\nstream\n" + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for object_id in sorted(objects):
        offsets[object_id] = len(out)
        out += f"{object_id} 0 obj\n".encode() + objects[object_id] + b"\nendobj\n"

    max_id = max(objects)
    xref_position = len(out)
    out += f"xref\n0 {max_id + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for object_id in range(1, max_id + 1):
        out += f"{offsets.get(object_id, 0):010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_position}\n%%EOF\n".encode()
    return bytes(out)
