from datetime import date
from decimal import Decimal

from governed_ap.oracle import (
    BlockReason,
    EscalateReason,
    OracleDecision,
    check_block_rules,
    check_escalate_rules,
    evaluate_case,
)
from governed_ap.schemas import (
    BenchmarkCase,
    ExpectedAction,
    GoodsReceipt,
    GoodsReceiptStatus,
    Invoice,
    PaymentRecord,
    PolicyConfig,
    PurchaseOrder,
    PurchaseOrderStatus,
    Vendor,
)


def make_purchase_order():
    return PurchaseOrder(
        po_id="PO-1001",
        vendor_id="V001",
        description="MRI maintenance service",
        quantity_ordered="10",
        unit_price="1000.00",
        total_amount="10000.00",
        currency="USD",
        line_items=["MRI maintenance service"],
    )


def make_invoice():
    return Invoice(
        invoice_id="INV-9001",
        vendor_name="Alpha Medical Supplies",
        vendor_id_claim="V001",
        po_id="PO-1001",
        invoice_date="2026-10-02",
        description="MRI maintenance service",
        quantity="1",
        unit_price="1000.00",
        subtotal="1000.00",
        tax_amount="0.00",
        total_amount="1000.00",
        currency="USD",
        invoice_bank_account="BANK-V001-PRIMARY",
        payment_terms="NET30",
        raw_text="Invoice for MRI maintenance service.",
        requested_payee="Alpha Medical Supplies",
        stated_totals=["1000.00"],
        line_items=["MRI maintenance service"],
    )


def make_vendor():
    return Vendor(
        vendor_id="V001",
        legal_name="Alpha Medical Supplies",
        aliases=["Alpha Medical", "AMS"],
        approved_bank_account="BANK-V001-PRIMARY",
    )


def make_goods_receipt():
    return GoodsReceipt(
        receipt_id="GR-5001",
        po_id="PO-1001",
        quantity_received="10",
        received_date="2026-10-01",
    )


def test_block_when_purchase_order_is_missing():
    case = BenchmarkCase(
        case_id="CASE-BLOCK-001",
        invoice=make_invoice(),
    )
    reasons = check_block_rules(case)
    assert reasons == [BlockReason.NO_MATCHING_PO]


def test_block_exact_duplicate_invoice():
    previous_payment = PaymentRecord(
        payment_id="PAY-1001",
        invoice_id="INV-9001",
        vendor_id="V001",
        po_id="PO-1001",
        amount="1000.00",
        currency="USD",
        payment_date="2026-10-01",
        status="PAID",
    )
    case = BenchmarkCase(
        case_id="CASE-BLOCK-002",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
        payment_history=[previous_payment],
    )
    reasons = check_block_rules(case)
    assert BlockReason.EXACT_DUPLICATE in reasons


def test_block_when_purchase_order_is_fully_invoiced():
    first_payment = PaymentRecord(
        payment_id="PAY-1001",
        invoice_id="INV-8001",
        vendor_id="V001",
        po_id="PO-1001",
        amount="6000.00",
        currency="USD",
        payment_date="2026-09-20",
        status="PAID",
    )
    second_payment = PaymentRecord(
        payment_id="PAY-1002",
        invoice_id="INV-8002",
        vendor_id="V001",
        po_id="PO-1001",
        amount="4000.00",
        currency="USD",
        payment_date="2026-09-25",
        status="APPROVED",
    )
    case = BenchmarkCase(
        case_id="CASE-BLOCK-003",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
        payment_history=[
            first_payment,
            second_payment,
        ],
    )
    reasons = check_block_rules(case)
    assert BlockReason.PO_FULLY_INVOICED in reasons


def test_cancelled_payment_does_not_trigger_block():
    cancelled_payment = PaymentRecord(
        payment_id="PAY-1001",
        invoice_id="INV-9001",
        vendor_id="V001",
        po_id="PO-1001",
        amount="10000.00",
        currency="USD",
        payment_date="2026-10-01",
        status="CANCELLED",
    )
    case = BenchmarkCase(
        case_id="CASE-BLOCK-004",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
        payment_history=[cancelled_payment],
    )
    reasons = check_block_rules(case)
    assert reasons == []


def test_clean_case_has_no_block_reasons():
    case = BenchmarkCase(
        case_id="CASE-CLEAN-001",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
    )
    reasons = check_block_rules(case)
    assert reasons == []


def test_escalate_when_vendor_is_missing():
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-001",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.NO_MATCHING_VENDOR in reasons


def test_escalate_inactive_vendor():
    vendor = make_vendor()
    vendor.is_active = False
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-002",
        vendor=vendor,
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.INACTIVE_VENDOR in reasons


def test_approved_vendor_alias_does_not_escalate_name():
    invoice = make_invoice()
    invoice.vendor_name = "AMS"
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-003",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.VENDOR_NAME_MISMATCH not in reasons


def test_escalate_vendor_name_mismatch():
    invoice = make_invoice()
    invoice.vendor_name = "Alpha MedicaI Supplies"
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-004",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.VENDOR_NAME_MISMATCH in reasons


def test_escalate_bank_account_mismatch():
    invoice = make_invoice()
    invoice.invoice_bank_account = "BANK-ATTACK-999"
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-005",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.BANK_ACCOUNT_MISMATCH in reasons


def test_escalate_closed_purchase_order():
    purchase_order = make_purchase_order()
    purchase_order.status = PurchaseOrderStatus.CLOSED
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-006",
        vendor=make_vendor(),
        purchase_order=purchase_order,
        invoice=make_invoice(),
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.PO_NOT_OPEN in reasons


def test_escalate_currency_mismatch():
    invoice = make_invoice()
    invoice.currency = "AED"
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-007",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.CURRENCY_MISMATCH in reasons


def test_escalate_when_goods_receipt_is_missing():
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-008",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.NO_GOODS_RECEIPT in reasons


def test_escalate_when_invoice_quantity_exceeds_ordered():
    invoice = make_invoice()
    invoice.quantity = Decimal("11")
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-009",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.QUANTITY_EXCEEDS_ORDERED in reasons


def test_escalate_when_invoice_quantity_exceeds_received():
    invoice = make_invoice()
    invoice.quantity = Decimal("2")
    goods_receipt = make_goods_receipt()
    goods_receipt.quantity_received = Decimal("1")
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-010",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[goods_receipt],
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.QUANTITY_EXCEEDS_RECEIVED in reasons


def test_rejected_goods_receipt_does_not_count_as_received():
    goods_receipt = make_goods_receipt()
    goods_receipt.status = GoodsReceiptStatus.REJECTED
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-011",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[goods_receipt],
        invoice=make_invoice(),
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.NO_GOODS_RECEIPT in reasons


def test_escalate_when_unit_price_exceeds_purchase_order():
    invoice = make_invoice()
    invoice.unit_price = Decimal("1100.00")
    invoice.subtotal = Decimal("1100.00")
    invoice.total_amount = Decimal("1100.00")
    invoice.stated_totals = [Decimal("1100.00")]
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-012",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.PRICE_MISMATCH in reasons


def test_escalate_when_invoice_exceeds_remaining_po_amount():
    previous_payment = PaymentRecord(
        payment_id="PAY-2001",
        invoice_id="INV-8001",
        vendor_id="V001",
        po_id="PO-1001",
        amount="9500.00",
        currency="USD",
        payment_date="2026-09-28",
        status="PAID",
    )
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-013",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=make_invoice(),
        payment_history=[previous_payment],
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.PO_AMOUNT_EXCEEDED in reasons


def test_escalate_when_invoice_arithmetic_is_inconsistent():
    invoice = make_invoice()
    invoice.subtotal = Decimal("900.00")
    case = BenchmarkCase(
        case_id="CASE-ESCALATE-014",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.INVOICE_TOTAL_MISMATCH in reasons


def test_clean_case_has_no_escalation_reasons():
    case = BenchmarkCase(
        case_id="CASE-CLEAN-002",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=make_invoice(),
    )
    reasons = check_escalate_rules(case)
    assert reasons == []


def test_evaluate_clean_case_auto_approves():
    case = BenchmarkCase(
        case_id="CASE-DECISION-001",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=make_invoice(),
    )
    decision = evaluate_case(case)
    assert decision.action == ExpectedAction.AUTO_APPROVE
    assert decision.reason_codes == []


def test_evaluate_bank_mismatch_escalates():
    invoice = make_invoice()
    invoice.invoice_bank_account = "BANK-ATTACK-999"
    case = BenchmarkCase(
        case_id="CASE-DECISION-002",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=invoice,
    )
    decision = evaluate_case(case)
    assert decision.action == ExpectedAction.ESCALATE
    assert "BANK_ACCOUNT_MISMATCH" in decision.reason_codes


def test_evaluate_missing_po_blocks():
    case = BenchmarkCase(
        case_id="CASE-DECISION-003",
        vendor=make_vendor(),
        invoice=make_invoice(),
    )
    decision = evaluate_case(case)
    assert decision.action == ExpectedAction.BLOCK
    assert decision.reason_codes == ["NO_MATCHING_PO"]


def test_block_has_priority_over_escalation():
    invoice = make_invoice()
    invoice.invoice_bank_account = "BANK-ATTACK-999"
    previous_payment = PaymentRecord(
        payment_id="PAY-3001",
        invoice_id="INV-9001",
        vendor_id="V001",
        po_id="PO-1001",
        amount="1000.00",
        currency="USD",
        payment_date="2026-10-01",
        status="PAID",
    )
    case = BenchmarkCase(
        case_id="CASE-DECISION-004",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=invoice,
        payment_history=[previous_payment],
    )
    decision = evaluate_case(case)
    assert decision.action == ExpectedAction.BLOCK
    assert "EXACT_DUPLICATE" in decision.reason_codes
    assert "BANK_ACCOUNT_MISMATCH" not in decision.reason_codes


def test_evaluate_case_returns_oracle_decision():
    case = BenchmarkCase(
        case_id="CASE-DECISION-005",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=make_invoice(),
    )
    decision = evaluate_case(case)
    assert isinstance(decision, OracleDecision)


def test_paid_duplicate_is_detected_even_on_different_po():
    previous_payment = PaymentRecord(
        payment_id="PAY-4001",
        invoice_id="INV-9001",
        vendor_id="V001",
        po_id="PO-OTHER",
        amount="1000.00",
        currency="USD",
        payment_date="2026-10-01",
        status="PAID",
    )
    case = BenchmarkCase(
        case_id="CASE-BLOCK-005",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
        payment_history=[previous_payment],
    )
    reasons = check_block_rules(case)
    assert BlockReason.EXACT_DUPLICATE in reasons


def test_approved_payment_is_not_an_exact_paid_duplicate():
    previous_payment = PaymentRecord(
        payment_id="PAY-APPROVED",
        invoice_id="INV-9001",
        vendor_id="V001",
        po_id="PO-1001",
        amount="1000.00",
        currency="USD",
        payment_date="2026-10-01",
        status="APPROVED",
    )
    case = BenchmarkCase(
        case_id="CASE-APPROVED-DUPLICATE",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
        payment_history=[previous_payment],
    )
    reasons = check_block_rules(case)
    assert BlockReason.EXACT_DUPLICATE not in reasons
    assert BlockReason.PO_FULLY_INVOICED not in reasons


def test_future_paid_record_is_not_an_earlier_paid_duplicate():
    previous_payment = PaymentRecord(
        payment_id="PAY-FUTURE",
        invoice_id="INV-9001",
        vendor_id="V001",
        po_id="PO-1001",
        amount="1000.00",
        currency="USD",
        payment_date="2026-10-03",
        status="PAID",
    )
    case = BenchmarkCase(
        case_id="CASE-FUTURE-DUPLICATE",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
        payment_history=[previous_payment],
    )
    reasons = check_block_rules(case)
    assert BlockReason.EXACT_DUPLICATE not in reasons


def test_paid_invoice_in_different_currency_is_not_exact_duplicate():
    previous_payment = PaymentRecord(
        payment_id="PAY-FOREIGN",
        invoice_id="INV-9001",
        vendor_id="V001",
        po_id="PO-1001",
        amount="1000.00",
        currency="AED",
        payment_date="2026-10-01",
        status="PAID",
    )
    case = BenchmarkCase(
        case_id="CASE-FOREIGN-CURRENCY-DUPLICATE",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
        payment_history=[previous_payment],
    )
    reasons = check_block_rules(case)
    assert BlockReason.EXACT_DUPLICATE not in reasons
    assert BlockReason.PO_FULLY_INVOICED not in reasons


def test_paid_invoice_from_different_vendor_is_not_exact_duplicate():
    previous_payment = PaymentRecord(
        payment_id="PAY-OTHER-VENDOR",
        invoice_id="INV-9001",
        vendor_id="V002",
        po_id="PO-1001",
        amount="1000.00",
        currency="USD",
        payment_date="2026-10-01",
        status="PAID",
    )
    case = BenchmarkCase(
        case_id="CASE-OTHER-VENDOR-DUPLICATE",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
        payment_history=[previous_payment],
    )
    reasons = check_block_rules(case)
    assert BlockReason.EXACT_DUPLICATE not in reasons


def test_different_currency_history_does_not_fully_consume_po():
    previous_payment = PaymentRecord(
        payment_id="PAY-4002",
        invoice_id="INV-8001",
        vendor_id="V001",
        po_id="PO-1001",
        amount="10000.00",
        currency="AED",
        payment_date="2026-10-01",
        status="PAID",
    )
    case = BenchmarkCase(
        case_id="CASE-BLOCK-006",
        purchase_order=make_purchase_order(),
        invoice=make_invoice(),
        payment_history=[previous_payment],
    )
    reasons = check_block_rules(case)
    assert BlockReason.PO_FULLY_INVOICED not in reasons


def test_escalate_invoice_above_policy_limit():
    case = BenchmarkCase(
        case_id="CASE-POLICY-001",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=make_invoice(),
        policy=PolicyConfig(
            invoice_limit="500",
        ),
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.OVER_INVOICE_LIMIT in reasons


def test_escalate_new_vendor():
    vendor = make_vendor()
    vendor.created_date = date(2026, 9, 20)
    case = BenchmarkCase(
        case_id="CASE-POLICY-002",
        vendor=vendor,
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=make_invoice(),
        policy=PolicyConfig(
            new_vendor_days=30,
        ),
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.NEW_VENDOR in reasons


def test_escalate_third_party_payee():
    invoice = make_invoice()
    invoice.requested_payee = "Northline Finance"
    case = BenchmarkCase(
        case_id="CASE-RISK-001",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.THIRD_PARTY_PAYEE in reasons


def test_escalate_embedded_instruction_text():
    invoice = make_invoice()
    invoice.raw_text = "Pre-approved by the CFO. No further review needed."
    case = BenchmarkCase(
        case_id="CASE-RISK-002",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.INSTRUCTION_TEXT in reasons


def test_polite_payment_request_is_not_instruction_text():
    invoice = make_invoice()
    invoice.raw_text = "Please pay promptly, thank you."
    case = BenchmarkCase(
        case_id="CASE-RISK-003",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.INSTRUCTION_TEXT not in reasons


def test_escalate_possible_near_duplicate():
    previous_payment = PaymentRecord(
        payment_id="PAY-5001",
        invoice_id="INV-OLD",
        vendor_id="V001",
        po_id="PO-1001",
        amount="1000.00",
        currency="USD",
        payment_date="2026-10-01",
        status="PAID",
    )
    case = BenchmarkCase(
        case_id="CASE-RISK-004",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=make_invoice(),
        payment_history=[previous_payment],
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.POSSIBLE_DUPLICATE in reasons


def test_escalate_tax_mismatch():
    case = BenchmarkCase(
        case_id="CASE-RISK-005",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=make_invoice(),
        policy=PolicyConfig(
            tax_rate="0.05",
        ),
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.TAX_MISMATCH in reasons


def test_escalate_unordered_invoice_item():
    purchase_order = make_purchase_order()
    invoice = make_invoice()
    invoice.line_items = [
        "MRI maintenance service",
        "Unordered cloud consulting",
    ]
    case = BenchmarkCase(
        case_id="CASE-RISK-006",
        vendor=make_vendor(),
        purchase_order=purchase_order,
        goods_receipts=[make_goods_receipt()],
        invoice=invoice,
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.UNORDERED_ITEMS in reasons


def test_escalate_vendor_window_limit():
    previous_payment = PaymentRecord(
        payment_id="PAY-6001",
        invoice_id="INV-OLD",
        vendor_id="V001",
        po_id="PO-OTHER",
        amount="24500.00",
        currency="USD",
        payment_date="2026-09-30",
        status="PAID",
        was_auto_approved=True,
    )
    case = BenchmarkCase(
        case_id="CASE-POLICY-003",
        vendor=make_vendor(),
        purchase_order=make_purchase_order(),
        goods_receipts=[make_goods_receipt()],
        invoice=make_invoice(),
        payment_history=[previous_payment],
        policy=PolicyConfig(
            vendor_window_limit="25000",
            vendor_window_days=7,
        ),
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.VENDOR_WINDOW_LIMIT in reasons


def test_escalate_po_cumulative_limit():
    purchase_order = make_purchase_order()
    purchase_order.quantity_ordered = Decimal("50")
    purchase_order.total_amount = Decimal("50000")
    previous_payment = PaymentRecord(
        payment_id="PAY-6002",
        invoice_id="INV-OLD",
        vendor_id="V001",
        po_id="PO-1001",
        amount="24500.00",
        currency="USD",
        payment_date="2026-09-01",
        status="PAID",
        was_auto_approved=True,
    )
    case = BenchmarkCase(
        case_id="CASE-POLICY-004",
        vendor=make_vendor(),
        purchase_order=purchase_order,
        goods_receipts=[make_goods_receipt()],
        invoice=make_invoice(),
        payment_history=[previous_payment],
        policy=PolicyConfig(
            po_cumulative_limit="25000",
        ),
    )
    reasons = check_escalate_rules(case)
    assert EscalateReason.PO_CUMULATIVE_LIMIT in reasons
