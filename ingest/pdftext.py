"""PDF -> plain text, locally. Statements from BoA and payroll systems are
digital PDFs with a text layer, so OCR is only a fallback for scanned pages."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pdfplumber

MIN_PAGE_CHARS = 25


def _ocr_page(pdf: Path, page_no: int) -> str | None:
    """OCR one page with poppler + tesseract CLIs, if both are installed."""
    if not (shutil.which("pdftoppm") and shutil.which("tesseract")):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        subprocess.run(
            ["pdftoppm", "-r", "300", "-png", "-f", str(page_no), "-l", str(page_no), str(pdf), str(prefix)],
            check=True,
            capture_output=True,
        )
        image = next(Path(tmp).glob("page*.png"))
        out = subprocess.run(["tesseract", str(image), "-", "--psm", "6"], check=True, capture_output=True, text=True)
        return out.stdout


def pdf_to_text(pdf: Path) -> tuple[str, list[str]]:
    """Return (text, warnings). Pages are separated by a marker line."""
    pages, warnings = [], []
    with pdfplumber.open(pdf) as doc:
        for i, page in enumerate(doc.pages, start=1):
            text = page.extract_text(layout=True) or ""
            if len(text.strip()) < MIN_PAGE_CHARS:
                ocr = _ocr_page(pdf, i)
                if ocr is None:
                    warnings.append(f"page {i} has no text layer and tesseract is not installed; skipped")
                    text = ""
                else:
                    warnings.append(f"page {i} was OCR'd")
                    text = ocr
            # layout=True pads with long runs of spaces; trim trailing ones.
            lines = [ln.rstrip() for ln in text.splitlines()]
            pages.append("\n".join(ln for ln in lines if ln))
    return "\n".join(f"===== PAGE {n} =====\n{p}" for n, p in enumerate(pages, start=1)), warnings
