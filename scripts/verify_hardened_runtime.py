"""Exercise the real invoice HTTP API inside an isolated, read-only Docker container.

CI passes this script to Python through docker exec stdin. Only standard-library
modules are used because the final runtime image does not install test tools.
All invoice documents are fictional; no payment service or LLM is contacted.
"""

import http.client
import json
import os
import tempfile
import time
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000
ENDPOINT = "/v1/invoices/assess"
BOUNDARY = "ci-hardened-invoice-fixture"


def request(method: str, path: str, *, body: bytes | None = None, key: bool = False):
    """Send one request to the API's loopback interface (no external network)."""
    headers = {}
    if key:
        headers["X-API-Key"] = os.environ["GOVERNED_AP_API_KEY"]
    if body is not None:
        headers["Content-Type"] = f"multipart/form-data; boundary={BOUNDARY}"
    connection = http.client.HTTPConnection(HOST, PORT, timeout=120)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        status = response.status
        data = json.loads(response.read().decode("utf-8"))
        return status, data
    finally:
        connection.close()


def multipart_pdf(pdf_bytes: bytes) -> bytes:
    """Wrap fixed fictional fixture bytes as one multipart PDF upload."""
    prefix = (
        f"--{BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="file"; filename="invoice.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("ascii")
    suffix = f"\r\n--{BOUNDARY}--\r\n".encode("ascii")
    return prefix + pdf_bytes + suffix


def assert_review_only(result: dict) -> None:
    """The HTTP boundary must never authorize or execute a payment."""
    assert result["action"] == "ESCALATE", result
    assert result["human_review_required"] is True, result
    assert result["payment_executed"] is False, result
    assert result["governance_agent_invoked"] is False, result


def main() -> None:
    assert os.getuid() == 10001, "Expected the unprivileged runtime user"

    # /tmp is the only writable scratch location; the application home stays read-only.
    with tempfile.TemporaryFile(dir="/tmp") as temp:
        temp.write(b"fictional CI scratch test")
    try:
        (Path.home() / "ci-should-not-write").write_text("unexpected", encoding="utf-8")
    except OSError:
        pass
    else:
        raise AssertionError("Container home unexpectedly writable")

    for attempt in range(30):
        try:
            status, data = request("GET", "/health")
            assert status == 200 and data["status"] == "ok", (status, data)
            break
        except (OSError, TimeoutError, ConnectionError):
            if attempt == 29:
                raise
            time.sleep(1)
    else:
        raise AssertionError("API did not become ready")

    invalid = multipart_pdf(b"%PDF-1.4\ninvalid test document")
    status, _ = request("POST", ENDPOINT, body=invalid)
    assert status == 401, f"Unauthenticated upload returned {status}"

    status, result = request("POST", ENDPOINT, body=invalid, key=True)
    assert status == 200, (status, result)
    assert_review_only(result)
    assert result["source"] == "ERROR", result

    fixture = Path("/fixtures/ci_fictional_scanned_invoice.pdf")
    assert fixture.is_file(), "Fictional scanned-PDF fixture not mounted"
    status, result = request("POST", ENDPOINT, body=multipart_pdf(fixture.read_bytes()), key=True)
    assert status == 200, (status, result)
    assert result["source"] == "OCR", result
    assert result["extracted"]["invoice_number"] == "TEST-2026-001", result
    assert result["extracted"]["currency"] == "AED", result
    assert result["extracted"]["total"] == "63.00", result
    assert_review_only(result)
    print("PASS: isolated, read-only, non-root runtime; auth; fail-closed PDF; real OCR")


if __name__ == "__main__":
    main()
