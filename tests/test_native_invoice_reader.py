from datetime import date
from decimal import Decimal

from pypdf import PdfWriter

from governed_ap.native_invoice_reader import (
    parse_native_text,
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
