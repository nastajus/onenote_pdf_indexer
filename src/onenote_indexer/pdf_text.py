from __future__ import annotations

from io import BytesIO
from typing import Any

from pypdf import PdfReader


def extract_pdf_text(pdf_bytes: bytes) -> dict[str, Any]:
    reader = PdfReader(BytesIO(pdf_bytes))
    pages: list[dict[str, Any]] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(
            {
                "page_number": index,
                "text": text,
                "char_count": len(text),
            }
        )

    return {
        "page_count": len(reader.pages),
        "char_count": sum(page["char_count"] for page in pages),
        "pages": pages,
    }

