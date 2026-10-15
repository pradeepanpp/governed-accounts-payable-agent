"""Offline tests for the local dashboard's HTTP boundary (no API calls)."""

import httpx
import pytest

from dashboard.client import ASSESSMENT_URL, DashboardError, assess_invoice

KEY = "a" * 48
PDF = b"%PDF-1.4\nfictional"


def assessment_payload():
    return {
        "action": "ESCALATE",
        "human_review_required": True,
        "payment_executed": False,
        "governance_agent_invoked": False,
        "source": "OCR",
        "reason_codes": ["TRUSTED_ERP_CONTEXT_MISSING"],
        "extracted": {"invoice_number": "TEST-2026-001", "currency": "AED", "total": "63.00"},
    }


@pytest.mark.parametrize("bad_pdf", [b"", b"just some text"])
def test_rejects_invalid_file_without_http(bad_pdf):
    with pytest.raises(DashboardError):
        assess_invoice(bad_pdf, KEY)


def test_rejects_missing_key_without_http():
    with pytest.raises(DashboardError, match="configured local API key"):
        assess_invoice(PDF, "short")


def test_success_sends_pdf_and_key_only_to_loopback():
    def handler(request):
        assert str(request.url) == ASSESSMENT_URL
        assert request.method == "POST"
        assert request.headers["X-API-Key"] == KEY
        assert b"fictional-invoice.pdf" in request.read()
        assert PDF in request.content
        return httpx.Response(200, json=assessment_payload())

    result = assess_invoice(PDF, KEY, transport=httpx.MockTransport(handler))
    assert result["action"] == "ESCALATE"
    assert result["payment_executed"] is False


@pytest.mark.parametrize("status", [401, 429, 503])
def test_http_errors_are_safe_and_do_not_include_key(status):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text="private"))
    with pytest.raises(DashboardError) as exc:
        assess_invoice(PDF, KEY, transport=transport)
    assert KEY not in str(exc.value)
    assert "private" not in str(exc.value)


@pytest.mark.parametrize("change", [{"action": "AUTO_APPROVE"}, {"payment_executed": True}])
def test_contract_violation_fails_closed(change):
    payload = {**assessment_payload(), **change}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(DashboardError, match="Unexpected API safety response"):
        assess_invoice(PDF, KEY, transport=transport)


def test_malformed_response_fails_closed():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="broken JSON"))
    with pytest.raises(DashboardError, match="unreadable"):
        assess_invoice(PDF, KEY, transport=transport)
