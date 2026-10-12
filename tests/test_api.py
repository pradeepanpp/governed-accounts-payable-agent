"""Offline API tests; no OCR binary, external service, or paid model needed."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import governed_ap.api as api
from governed_ap.api import MAX_HTTP_BODY_BYTES
from governed_ap.native_invoice_reader import MAX_PDF_BYTES, PartialInvoice
from governed_ap.pdf_intake import PDFIntakeResult
from governed_ap.schemas import ExpectedAction

client = TestClient(api.app)
VALID_HEADER = b"%PDF-1.4\n%synthetic\n"
URL = "/v1/invoices/assess"

TEST_API_KEY = "test-only-key-not-for-real-use-123456789"


@pytest.fixture(autouse=True)
def configure_test_api_key(monkeypatch):
    """Provide fake authentication for every API test."""
    monkeypatch.setenv("GOVERNED_AP_API_KEY", TEST_API_KEY)


def upload(
    data=VALID_HEADER,
    media_type="application/pdf",
    filename="untrusted.pdf",
    headers=None,
):
    if headers is None:
        headers = {"X-API-Key": TEST_API_KEY}

    return client.post(
        URL,
        files={"file": (filename, data, media_type)},
        headers=headers,
    )


def test_health_does_not_claim_payment_or_ocr_readiness():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "read_only_document_intake",
    }


def test_pdf_is_passed_to_existing_intake_with_no_erp_context(monkeypatch):
    observed = {}

    def fake_assess(path: Path):
        observed["bytes"] = path.read_bytes()
        observed["name"] = path.name
        return PDFIntakeResult(
            action=ExpectedAction.ESCALATE,
            source="NATIVE",
            extracted=PartialInvoice(
                invoice_number="INV-TEST",
                currency="AED",
                total="63.00",
            ),
            reason_codes=(
                "TRUSTED_ERP_CONTEXT_MISSING",
                "REQUIRED_AP_FIELDS_UNVERIFIED",
            ),
        )

    monkeypatch.setattr(api, "assess_pdf", fake_assess)
    response = upload(filename="../../do-not-trust-filename.pdf")

    assert response.status_code == 200
    assert observed == {
        "bytes": VALID_HEADER,
        "name": "invoice.pdf",
    }

    result = response.json()

    assert result["action"] == "ESCALATE"
    assert result["human_review_required"] is True
    assert result["payment_executed"] is False
    assert result["governance_agent_invoked"] is False
    assert result["source"] == "NATIVE"
    assert result["extracted"]["total"] == "63.00"
    assert "REQUIRED_AP_FIELDS_UNVERIFIED" in result["reason_codes"]


def test_api_still_escalates_even_if_intake_regresses_to_approval(monkeypatch):
    def fake_assess(path: Path):
        return PDFIntakeResult(
            action=ExpectedAction.AUTO_APPROVE,
            source="OCR",
            extracted=PartialInvoice(),
            reason_codes=(),
        )

    monkeypatch.setattr(api, "assess_pdf", fake_assess)
    response = upload()

    assert response.status_code == 200
    assert response.json()["action"] == "ESCALATE"
    assert response.json()["human_review_required"] is True


@pytest.mark.parametrize(
    ("data", "media_type", "expected_status"),
    [
        (VALID_HEADER, "image/png", 415),
        (b"", "application/pdf", 400),
        (b"not-a-pdf", "application/pdf", 422),
        (b"%PDF-" + b"x" * MAX_PDF_BYTES, "application/pdf", 413),
    ],
    ids=[
        "unsupported-file-type",
        "empty-file",
        "invalid-pdf-signature",
        "oversized-pdf",
    ],
)
def test_invalid_uploads_rejected(data, media_type, expected_status):
    assert upload(data, media_type).status_code == expected_status


def test_missing_file_is_rejected():
    response = client.post(
        URL,
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 422


def test_corrupted_pdf_is_review_only():
    response = upload(b"%PDF-1.4\ncorrupt document\n")

    assert response.status_code == 200

    result = response.json()
    assert result["action"] == "ESCALATE"
    assert result["source"] == "ERROR"
    assert "DOCUMENT_INTAKE_FAILURE" in result["reason_codes"]


def test_unexpected_assessment_failure_never_returns_approval(monkeypatch):
    def fails(path: Path):
        raise RuntimeError("internal private message")

    monkeypatch.setattr(api, "assess_pdf", fails)
    response = upload()

    assert response.status_code == 503
    assert "internal private message" not in response.text


def test_parallel_ocr_request_rejected_while_busy():
    assert api._assessment_slot.acquire(blocking=False)

    try:
        response = upload()
        assert response.status_code == 429
    finally:
        api._assessment_slot.release()


def test_missing_api_key_is_rejected():
    response = upload(headers={})

    assert response.status_code == 401
    assert "API key" in response.json()["detail"]


def test_incorrect_api_key_is_rejected():
    response = upload(
        headers={"X-API-Key": "incorrect-key"},
    )

    assert response.status_code == 401


def test_unconfigured_api_key_fails_closed(monkeypatch):
    monkeypatch.delenv(
        "GOVERNED_AP_API_KEY",
        raising=False,
    )

    response = upload()

    assert response.status_code == 503


def test_short_api_key_configuration_is_rejected(monkeypatch):
    monkeypatch.setenv(
        "GOVERNED_AP_API_KEY",
        "short-key",
    )

    response = upload()

    assert response.status_code == 503


def test_http_body_limit_rejects_oversized_request():
    # Larger than the allowed complete HTTP request body.
    oversized = b"%PDF-" + b"x" * MAX_HTTP_BODY_BYTES

    response = upload(oversized)

    assert response.status_code == 413


def test_audit_log_omits_invoice_details(monkeypatch):
    events = []

    def capture_log(message, *args):
        events.append(message % args)

    monkeypatch.setattr(api.audit_logger, "info", capture_log)

    def fake_assess(path: Path):
        return PDFIntakeResult(
            action=ExpectedAction.ESCALATE,
            source="NATIVE",
            extracted=PartialInvoice(
                invoice_number="INV-CONFIDENTIAL-001",
                total="63.00",
            ),
            reason_codes=("TRUSTED_ERP_CONTEXT_MISSING",),
        )

    monkeypatch.setattr(api, "assess_pdf", fake_assess)

    response = upload()

    assert response.status_code == 200

    records = [json.loads(event) for event in events]

    assessment = next(record for record in records if record["event"] == "assessment_completed")

    http_request = next(record for record in records if record["event"] == "http_request")

    request_id = response.headers["X-Request-ID"]

    assert assessment["request_id"] == request_id
    assert http_request["request_id"] == request_id
    assert assessment["source"] == "NATIVE"
    assert assessment["action"] == "ESCALATE"

    logged_text = json.dumps(records)

    assert "INV-CONFIDENTIAL-001" not in logged_text
    assert TEST_API_KEY not in logged_text


def test_request_ids_are_unique_and_cover_authentication_failures():
    first = client.get("/health")
    second = client.get("/health")
    unauthorized = upload(headers={})

    assert unauthorized.status_code == 401

    request_ids = [response.headers["X-Request-ID"] for response in (first, second, unauthorized)]

    assert len(set(request_ids)) == 3
    assert all(len(request_id) == 32 for request_id in request_ids)
