"""Shared PDF helpers for playbook single and bulk import."""

from __future__ import annotations

import os
import uuid


def pymupdf_available():
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


def pdf_page_count(pdf_path):
    import fitz

    doc = fitz.open(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def render_pdf_pages(
    pdf_path,
    output_dir,
    *,
    url_prefix,
    dpi=150,
    first_page=1,
    last_page=None,
    max_pages=None,
):
    """Render PDF pages to PNG files.

    Returns list of dicts: file_path, url, page (1-based), index (0-based).
    """
    import fitz

    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    images = []
    try:
        start = max(1, int(first_page))
        end = len(doc) if last_page is None else min(len(doc), int(last_page))
        for page_num in range(start, end + 1):
            if max_pages is not None and len(images) >= max_pages:
                break
            page = doc[page_num - 1]
            pix = page.get_pixmap(dpi=dpi)
            img_name = f"{uuid.uuid4().hex}.png"
            img_path = os.path.join(output_dir, img_name)
            pix.save(img_path)
            images.append(
                {
                    "file_path": img_path,
                    "url": f"{url_prefix}/{img_name}",
                    "page": page_num,
                    "index": len(images),
                }
            )
    finally:
        doc.close()
    return images


def require_pymupdf():
    if not pymupdf_available():
        raise ImportError(
            "PyMuPDF is required for playbook PDF import. "
            "Install it with: pip install pymupdf"
        )
