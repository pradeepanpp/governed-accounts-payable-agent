"""Conservative local HTTP client for the read-only invoice assessment API."""

from typing import Any

import httpx

# This is deliberately a fixed loopback endpoint, not a user-provided URL.
# No API key or document is sent to a remote service.
ASSESSMENT_URL = "http://127.0.0.1:8000/v1/invoices/assess"
MAX_PDF_BYTES = 15_000_000


class DashboardError(Exception):
    """Safe error shown to the local dashboard user without leaking secrets."""


def assess_invoice(
    pdf_bytes: bytes,
    api_key: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Send one fictional PDF to the existing local API; never authorize payments."""
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes:
        raise DashboardError("Choose a nonempty PDF file.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise DashboardError("PDF exceeds the API's 15 MB limit.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise DashboardError("The selected file does not have a PDF signature.")
    if not api_key or len(api_key) < 32:
        raise DashboardError("Start the dashboard with a configured local API key.")

    try:
        # trust_env=False prevents system HTTP proxy settings from rerouting
        # a request that should stay entirely on the local computer.
        with httpx.Client(
            timeout=httpx.Timeout(90.0, connect=3.0),
            trust_env=False,
            transport=transport,
        ) as client:
            response = client.post(
                ASSESSMENT_URL,
                headers={"X-API-Key": api_key},
                files={"file": ("fictional-invoice.pdf", pdf_bytes, "application/pdf")},
            )
    except httpx.TimeoutException as error:
        raise DashboardError("Local assessment timed out; no approval was granted.") from error
    except httpx.RequestError as error:
        raise DashboardError("Cannot reach the local assessment API at port 8000.") from error

    if response.status_code == 401:
        raise DashboardError("The local API rejected the configured key.")
    if response.status_code == 429:
        raise DashboardError("The assessment API is busy. Try again later.")
    if response.status_code == 413:
        raise DashboardError("The assessment API rejected the oversized PDF.")
    if response.status_code != 200:
        raise DashboardError(
            f"Assessment unavailable (HTTP {response.status_code}); human review is required."
        )

    try:
        result = response.json()
    except ValueError as error:
        raise DashboardError("The API returned an unreadable response.") from error

    # Fail closed if the API contract unexpectedly changes. We must never
    # present an approval or a purported payment as a safe dashboard result.
    if (
        not isinstance(result, dict)
        or result.get("action") != "ESCALATE"
        or result.get("human_review_required") is not True
        or result.get("payment_executed") is not False
        or result.get("governance_agent_invoked") is not False
        or result.get("source") not in {"NATIVE", "OCR", "ERROR"}
        or not isinstance(result.get("extracted"), dict)
        or not isinstance(result.get("reason_codes"), list)
        or not all(isinstance(code, str) for code in result["reason_codes"])
    ):
        raise DashboardError("Unexpected API safety response; do not act on this document.")

    return result
