"""Conservative native-PDF invoice extraction and fixture audit."""

import argparse
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

MAX_PDF_BYTES = 15_000_000
MAX_PDF_PAGES = 10
MAX_TEXT_CHARS = 64_000

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
    """Only fields observed in a PDF, not trusted ERP information."""

    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = None
    invoice_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    subtotal: Decimal | None = Field(default=None, ge=0)
    tax: Decimal | None = Field(default=None, ge=0)
    total: Decimal | None = Field(default=None, gt=0)


def _unique_match(
    lines: list[str],
    pattern: re.Pattern[str],
) -> str | None:
    matches = [match.group(1) for line in lines if (match := pattern.fullmatch(line))]

    if not matches:
        return None

    # Repeated identical headers are normal in multipage invoices.
    if len(set(matches)) == 1:
        return matches[0]

    # Conflicting values must not be guessed.
    return None


def _money_after(
    lines: list[str],
    label: str,
    currency: str | None,
) -> Decimal | None:
    matches: list[Decimal] = []

    for index, line in enumerate(lines[:-1]):
        if label == "tax":
            is_label = line.lower().startswith(("vat ", "tax ")) or line.lower() in {"tax", "vat"}
        else:
            is_label = line.casefold() == label.casefold()

        if not is_label:
            continue

        found = MONEY.fullmatch(lines[index + 1])

        if found and currency == found.group(1):
            matches.append(Decimal(found.group(2).replace(",", "")))

    return matches[0] if len(matches) == 1 else None


def parse_native_text(text: str) -> PartialInvoice:
    """Extract supported fields without following document instructions."""
    if len(text) > MAX_TEXT_CHARS or "\x00" in text:
        raise ValueError("Unexpected or oversized PDF text")

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    return PartialInvoice(
        invoice_number=_unique_match(lines, INVOICE_NUMBER),
        invoice_date=_unique_match(lines, DATE),
        currency=_unique_match(lines, CURRENCY),
        subtotal=_money_after(
            lines,
            "subtotal",
            _unique_match(lines, CURRENCY),
        ),
        tax=_money_after(
            lines,
            "tax",
            _unique_match(lines, CURRENCY),
        ),
        total=_money_after(
            lines,
            "total",
            _unique_match(lines, CURRENCY),
        ),
    )


def read_pdf_text(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > MAX_PDF_BYTES:
        raise ValueError("PDF missing or above the size limit")

    reader = PdfReader(str(path), strict=True)

    if not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
        raise ValueError("Invalid PDF page count")

    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("Extracted text is too long")

    return text


def audit_fixtures(fixtures: Path) -> None:
    """Use reference JSON only for scoring, never for extraction."""
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
            text = read_pdf_text(folder / "invoice.pdf")

            if not text.strip():
                print(f"{folder.name:<23} {'OCR_REQUIRED':<18} {'--':>8}")
                continue

            predicted = parse_native_text(text)

            truth = json.loads((folder / "expected.json").read_text(encoding="utf-8"))

            actual = [getattr(predicted, name) for name in fields]
            expected = [truth[name] for name in expected_keys]

            matches = sum(
                (value is not None and str(value) == str(reference))
                if isinstance(value, (str, date))
                else (value is not None and value == Decimal(str(reference)))
                for value, reference in zip(actual, expected, strict=True)
            )

            print(f"{folder.name:<23} {'PARTIAL_REVIEW':<18} {matches:>5}/6")

        except (
            OSError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            print(f"{folder.name:<23} ERROR: {error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixtures", type=Path)
    args = parser.parse_args()

    audit_fixtures(args.fixtures)


if __name__ == "__main__":
    main()
