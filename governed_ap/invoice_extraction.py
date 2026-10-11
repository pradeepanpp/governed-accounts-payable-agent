"""Strict offline extraction for a controlled, labeled synthetic invoice format."""

import json
from typing import Any

from pydantic import ValidationError

from governed_ap.schemas import BenchmarkCase, Invoice

MAX_INVOICE_TEXT_LENGTH = 64_000

# Exact field order prevents fuzzy matching and silent duplicate selection.
_FIELDS = (
    ("Invoice ID", "invoice_id"),
    ("Vendor Name", "vendor_name"),
    ("Vendor ID Claim", "vendor_id_claim"),
    ("PO ID", "po_id"),
    ("Invoice Date", "invoice_date"),
    ("Description", "description"),
    ("Quantity", "quantity"),
    ("Unit Price", "unit_price"),
    ("Subtotal", "subtotal"),
    ("Tax Amount", "tax_amount"),
    ("Total Amount", "total_amount"),
    ("Currency", "currency"),
    ("Invoice Bank Account", "invoice_bank_account"),
    ("Payment Terms", "payment_terms"),
    ("Requested Payee", "requested_payee"),
    ("Stated Totals", "stated_totals"),
    ("Line Items", "line_items"),
)

_JSON_FIELDS = {"requested_payee", "stated_totals", "line_items"}


class InvoiceIntakeError(ValueError):
    """Invoice cannot safely enter the governed decision pipeline."""


def render_invoice_text(invoice: Invoice) -> str:
    """Create a labeled-text fixture from a synthetic structured invoice."""
    lines: list[str] = []

    for label, field_name in _FIELDS:
        value = getattr(invoice, field_name)

        if field_name == "stated_totals":
            serialized = json.dumps([str(item) for item in value])
        elif field_name in _JSON_FIELDS:
            serialized = json.dumps(value, ensure_ascii=False)
        else:
            serialized = str(value)

        if any(char in serialized for char in ("\r", "\n", "\x00")):
            raise InvoiceIntakeError(f"Invalid line break in {label}")

        lines.append(f"{label}: {serialized}")

    lines.extend(("Notes:", invoice.raw_text))
    text = "\n".join(lines)

    if len(text) > MAX_INVOICE_TEXT_LENGTH:
        raise InvoiceIntakeError("Invoice text exceeds maximum length")

    return text


def parse_invoice_text(text: str) -> Invoice:
    """Parse labeled invoice data without obeying embedded instructions."""
    if not isinstance(text, str) or len(text) > MAX_INVOICE_TEXT_LENGTH or "\x00" in text:
        raise InvoiceIntakeError("Invoice text is missing or too long")

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    if len(lines) < len(_FIELDS) + 2:
        raise InvoiceIntakeError("Invoice is missing required fields or notes")

    values: dict[str, Any] = {}

    for index, (label, field_name) in enumerate(_FIELDS):
        prefix = f"{label}: "

        if not lines[index].startswith(prefix):
            raise InvoiceIntakeError(f"Missing or out-of-order field: {label}")

        raw_value = lines[index][len(prefix) :]

        if field_name in _JSON_FIELDS:
            try:
                values[field_name] = json.loads(raw_value)
            except json.JSONDecodeError as error:
                raise InvoiceIntakeError(f"Invalid JSON in {label}") from error
        else:
            values[field_name] = raw_value

    if lines[len(_FIELDS)] != "Notes:":
        raise InvoiceIntakeError("Notes boundary is missing or invoice has extra headers")

    notes = "\n".join(lines[len(_FIELDS) + 1 :])

    if not notes.strip():
        raise InvoiceIntakeError("Notes must not be empty")

    # Prevent additional field-like claims hidden inside free text.
    for line in notes.splitlines():
        if any(line.startswith(f"{label}: ") for label, _ in _FIELDS):
            raise InvoiceIntakeError("Conflicting invoice header found in notes")

    # Give the guardrail the complete untrusted supplier document.
    values["raw_text"] = text

    try:
        return Invoice.model_validate(values)
    except ValidationError as error:
        fields = ", ".join(str(item["loc"][0]) for item in error.errors())
        raise InvoiceIntakeError(f"Invalid invoice fields: {fields}") from error


def case_from_invoice_text(
    trusted_case: BenchmarkCase,
    text: str,
) -> BenchmarkCase:
    """Replace only the invoice, preserving trusted ERP records."""
    invoice = parse_invoice_text(text)

    if (
        trusted_case.purchase_order is not None
        and invoice.po_id != trusted_case.purchase_order.po_id
    ):
        raise InvoiceIntakeError("Invoice PO ID conflicts with the trusted PO")

    return trusted_case.model_copy(
        update={"invoice": invoice},
        deep=True,
    )
