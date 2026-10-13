"""Conservative native-PDF extraction, offline OCR, and fixture evaluation."""

import argparse
import json
import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from time import monotonic

import pypdfium2 as pdfium
import pytesseract
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

# Limits for local document processing.
MAX_PDF_BYTES = 15_000_000
MAX_PDF_PAGES = 10
MAX_TEXT_CHARS = 64_000

# OCR configuration.
OCR_SCALE = 3.0
MAX_RENDER_PIXELS = 12_000_000
MAX_PAGE_OCR_SECONDS = 30.0
MAX_TOTAL_OCR_SECONDS = 60.0

# Patterns for supported English invoice layouts.
# Three decimal places allow currencies such as KWD.
MONEY = re.compile(r"^([A-Z]{3})\s+(\d[\d,]*(?:\.\d{1,3})?)$")
INVOICE_NUMBER = re.compile(
    r"^Invoice\s*:\s*(\S.*?)\s*$",
    re.IGNORECASE,
)
DATE = re.compile(
    r"^Date\s*:\s*(\d{4}-\d{2}-\d{2})\s*$",
    re.IGNORECASE,
)
CURRENCY = re.compile(
    r"^Currency\s*:\s*([A-Z]{3})\s*$",
    re.IGNORECASE,
)


class PartialInvoice(BaseModel):
    """Observed invoice fields; no trusted ERP values."""

    model_config = ConfigDict(extra="forbid")
    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )
    subtotal: Decimal | None = Field(default=None, ge=0)
    tax: Decimal | None = Field(default=None, ge=0)
    total: Decimal | None = Field(default=None, gt=0)


def _unique_match(
    lines: list[str],
    pattern: re.Pattern[str],
) -> str | None:
    """Return one value, allowing identical repeated headers."""

    matches = [match.group(1) for line in lines if (match := pattern.fullmatch(line))]
    if not matches:
        return None
    # Multipage invoices may repeat identical headers.
    if len(set(matches)) == 1:
        return matches[0]
    # Conflicting values are ambiguous.
    return None


def _money_after(
    lines: list[str],
    label: str,
    currency: str | None,
) -> Decimal | None:
    """Read a labeled amount only when its currency matches."""

    matches: list[Decimal] = []
    for index, line in enumerate(lines[:-1]):
        if label == "tax":
            lower_line = line.lower()
            is_label = lower_line.startswith(("vat ", "tax ")) or lower_line in {"tax", "vat"}
        else:
            is_label = line.casefold() == label.casefold()
        if not is_label:
            continue
        found = MONEY.fullmatch(lines[index + 1])
        if found and currency == found.group(1):
            amount = Decimal(found.group(2).replace(",", ""))
            matches.append(amount)
    # Do not guess when multiple candidates exist.
    return matches[0] if len(matches) == 1 else None


def parse_native_text(text: str) -> PartialInvoice:
    """Extract supported fields without obeying document instructions."""

    if not isinstance(text, str):
        raise ValueError("Invoice text must be a string")
    if len(text) > MAX_TEXT_CHARS or "\x00" in text:
        raise ValueError("Unexpected or oversized PDF text")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    currency = _unique_match(lines, CURRENCY)
    return PartialInvoice(
        invoice_number=_unique_match(
            lines,
            INVOICE_NUMBER,
        ),
        invoice_date=_unique_match(
            lines,
            DATE,
        ),
        currency=currency,
        subtotal=_money_after(
            lines,
            "subtotal",
            currency,
        ),
        tax=_money_after(
            lines,
            "tax",
            currency,
        ),
        total=_money_after(
            lines,
            "total",
            currency,
        ),
    )


def read_pdf_text(path: Path) -> str:
    """Extract selectable text from a PDF without OCR."""

    if not path.is_file() or path.stat().st_size > MAX_PDF_BYTES:
        raise ValueError("PDF missing or above the size limit")
    reader = PdfReader(str(path), strict=True)
    if not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
        raise ValueError("Invalid PDF page count")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("Extracted text is too long")
    return text


def read_invoice_pdf(
    path: Path,
    languages: str = "eng+ara",
) -> tuple[str, str]:
    """Extract native PDF text or fall back to local Tesseract OCR."""

    native_text = read_pdf_text(path)
    # Avoid OCR when selectable text already exists.
    if native_text.strip():
        return native_text, "NATIVE"
    supported_languages = {
        "eng",
        "ara",
        "eng+ara",
        "ara+eng",
    }
    if languages not in supported_languages:
        raise ValueError("Unsupported OCR language selection")
    # One shared processing budget across all scanned pages.
    deadline = monotonic() + MAX_TOTAL_OCR_SECONDS

    def remaining_ocr_time() -> float:
        """Return remaining seconds or reject an expired budget."""

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("OCR total time budget exceeded")
        return remaining

    # Allow the executable location to be configured externally.
    pytesseract.pytesseract.tesseract_cmd = os.environ.get(
        "TESSERACT_CMD",
        "tesseract",
    )
    # Optional directory containing trained language models.
    tessdata = os.environ.get("TESSDATA_DIR")
    config = "--psm 6"
    if tessdata:
        if not Path(tessdata).is_dir():
            raise ValueError("Tesseract language directory is missing")
        os.environ["TESSDATA_PREFIX"] = tessdata
    extracted_pages: list[str] = []
    # Render only PDFs that could not be read natively.
    with pdfium.PdfDocument(str(path)) as document:
        if not 1 <= len(document) <= MAX_PDF_PAGES:
            raise ValueError("Invalid PDF page count")
        for page_index in range(len(document)):
            remaining_ocr_time()
            page = document[page_index]
            try:
                width, height = page.get_size()
                pixel_count = width * height * OCR_SCALE**2
                if pixel_count > MAX_RENDER_PIXELS:
                    raise ValueError("PDF page too large for OCR")

                remaining_ocr_time()
                bitmap = page.render(scale=OCR_SCALE)
                try:
                    image = bitmap.to_pil().copy()
                finally:
                    bitmap.close()
                try:
                    page_text = pytesseract.image_to_string(
                        image,
                        lang=languages,
                        config=config,
                        timeout=min(
                            MAX_PAGE_OCR_SECONDS,
                            remaining_ocr_time(),
                        ),
                    )
                except (
                    pytesseract.TesseractError,
                    pytesseract.TesseractNotFoundError,
                    RuntimeError,
                ) as error:
                    raise ValueError(f"Local OCR failed: {error}") from error
                finally:
                    image.close()
                extracted_pages.append(page_text)
                remaining_ocr_time()
            finally:
                page.close()
    text = "\n".join(extracted_pages)
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("OCR output exceeds text limit")
    return text, "OCR"


def audit_fixtures(
    fixtures: Path,
    languages: str = "eng+ara",
) -> None:
    """Compare PDF extraction with reference JSON for evaluation only."""

    fields = (
        "invoice_number",
        "invoice_date",
        "currency",
        "subtotal",
        "tax",
        "total",
    )
    expected_keys = (
        "invoiceNumber",
        "invoiceDate",
        "currency",
        "subtotal",
        "tax",
        "total",
    )
    print(f"{'Fixture':<23} {'Status':<18} {'Correct':>8}")
    for folder in sorted(fixtures.iterdir()):
        if not folder.is_dir():
            continue
        try:
            pdf_path = folder / "invoice.pdf"
            json_path = folder / "expected.json"
            text, source = read_invoice_pdf(
                pdf_path,
                languages=languages,
            )
            if not text.strip():
                print(f"{folder.name:<23} {'OCR_UNREADABLE':<18} {'--':>8}")
                continue
            # Extract fields from document text only.
            predicted = parse_native_text(text)
            # Load reference values only after extraction.
            truth = json.loads(json_path.read_text(encoding="utf-8"))
            actual = [getattr(predicted, name) for name in fields]
            expected = [truth[name] for name in expected_keys]
            matches = sum(
                (value is not None and str(value) == str(reference))
                if isinstance(value, (str, date))
                else (value is not None and value == Decimal(str(reference)))
                for value, reference in zip(
                    actual,
                    expected,
                    strict=True,
                )
            )
            # Every document remains subject to review.
            # OCR is not evidence of financial authorization.
            status = "OCR_REVIEW" if source == "OCR" else "PARTIAL_REVIEW"
            print(f"{folder.name:<23} {status:<18} {matches:>5}/6")
        except (
            OSError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            print(f"{folder.name:<23} ERROR: {error}")


def main() -> None:
    """Run the fixture audit from the command line."""

    parser = argparse.ArgumentParser(
        description=("Offline PDF invoice extraction and reference-field evaluation.")
    )
    parser.add_argument(
        "fixtures",
        type=Path,
        help="Directory containing invoice fixture folders.",
    )
    parser.add_argument(
        "--ocr-langs",
        default="eng+ara",
        choices=(
            "eng",
            "ara",
            "eng+ara",
            "ara+eng",
        ),
        help="Languages for local Tesseract OCR.",
    )
    args = parser.parse_args()
    audit_fixtures(
        args.fixtures,
        languages=args.ocr_langs,
    )


if __name__ == "__main__":
    main()
