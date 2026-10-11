from datetime import date
from decimal import Decimal
from pathlib import Path

import pytesseract
import pytest
from pypdf import PdfWriter

import governed_ap.native_invoice_reader as reader
from governed_ap.native_invoice_reader import (
    parse_native_text,
    read_invoice_pdf,
    read_pdf_text,
)

SAMPLE = """SYNTHETIC FIXTURE
Fictional Gulf Foods LLC
TAX INVOICE
Invoice: INV-2026-001
Date: 2026-08-01
Currency: AED
SKU
Description
Qty
Unit
Price
Total
SUP-WAT-330
Sparkling Water 330ml
24
EA
2.50
60.00
Subtotal
AED 60.00
VAT 5%
AED 3.00
Total
AED 63.00"""


def test_extracts_six_fields():
    result = parse_native_text(SAMPLE)

    assert result.invoice_number == "INV-2026-001"
    assert result.invoice_date == date(2026, 8, 1)
    assert result.currency == "AED"
    assert result.subtotal == Decimal("60.00")
    assert result.tax == Decimal("3.00")
    assert result.total == Decimal("63.00")


def test_ambiguous_total_is_not_guessed():
    text = SAMPLE + "\nTotal\nAED 1.00"
    result = parse_native_text(text)

    assert result.total is None


def test_missing_fields_remain_missing():
    result = parse_native_text("Invoice: INV-1\nDate: 2026-08-01")

    assert result.currency is None
    assert result.total is None


def test_image_only_pdf_has_no_native_text(tmp_path):
    path = tmp_path / "blank.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)

    with path.open("wb") as output:
        writer.write(output)

    assert read_pdf_text(path) == ""


def test_identical_repeated_headers_are_accepted():
    repeated = SAMPLE + "\nInvoice: INV-2026-001" + "\nDate: 2026-08-01" + "\nCurrency: AED"

    result = parse_native_text(repeated)

    assert result.invoice_number == "INV-2026-001"
    assert result.invoice_date == date(2026, 8, 1)
    assert result.currency == "AED"
    assert result.total == Decimal("63.00")


def test_conflicting_invoice_numbers_are_rejected():
    conflicting = SAMPLE + "\nInvoice: INV-DIFFERENT"

    result = parse_native_text(conflicting)

    assert result.invoice_number is None


def test_kwd_three_decimals_without_printed_tax():
    text = """Invoice: INV-2026-007
Date: 2026-08-07
Currency: KWD
Subtotal
KWD 46.500
Total
KWD 46.500
Notes
No VAT line is printed."""

    result = parse_native_text(text)

    assert result.currency == "KWD"
    assert result.subtotal == Decimal("46.500")
    assert result.total == Decimal("46.500")
    assert result.tax is None


def _blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)

    with path.open("wb") as output:
        writer.write(output)


def test_ocr_fallback_for_image_only_pdf(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "scan.pdf"
    _blank_pdf(path)

    monkeypatch.setattr(
        pytesseract,
        "image_to_string",
        lambda *args, **kwargs: SAMPLE,
    )

    text, source = read_invoice_pdf(path)

    assert source == "OCR"
    assert parse_native_text(text).invoice_number == "INV-2026-001"


def test_native_text_skips_ocr(monkeypatch):
    monkeypatch.setattr(
        reader,
        "read_pdf_text",
        lambda path: SAMPLE,
    )

    def unexpected_ocr(*args, **kwargs):
        raise AssertionError("OCR should not run")

    monkeypatch.setattr(
        pytesseract,
        "image_to_string",
        unexpected_ocr,
    )

    text, source = read_invoice_pdf(Path("unused.pdf"))

    assert source == "NATIVE"
    assert text == SAMPLE


def test_empty_ocr_does_not_invent_fields(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "unreadable.pdf"
    _blank_pdf(path)

    monkeypatch.setattr(
        pytesseract,
        "image_to_string",
        lambda *args, **kwargs: "",
    )

    text, source = read_invoice_pdf(path)
    invoice = parse_native_text(text)

    assert source == "OCR"
    assert invoice.invoice_number is None
    assert invoice.total is None


def test_missing_language_directory_fails_safely(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "scan.pdf"
    _blank_pdf(path)

    monkeypatch.setenv(
        "TESSDATA_DIR",
        str(tmp_path / "missing-models"),
    )

    with pytest.raises(
        ValueError,
        match="language directory is missing",
    ):
        read_invoice_pdf(path)
