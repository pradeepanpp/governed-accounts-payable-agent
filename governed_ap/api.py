"""Local-only, read-only PDF invoice assessment HTTP interface."""

import hmac
import json
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import perf_counter
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, Security, UploadFile
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from governed_ap.native_invoice_reader import MAX_PDF_BYTES, PartialInvoice
from governed_ap.pdf_intake import assess_pdf

# Reuse Uvicorn's configured logging output during server execution.
audit_logger = logging.getLogger("uvicorn.error")


def record_audit_event(
    event: str,
    request_id: str,
    *,
    is_error: bool = False,
    **details: str | int | float,
) -> None:
    """Write a structured event without document or credential contents."""

    record = {
        "event": event,
        "request_id": request_id,
        **details,
    }

    message = json.dumps(record, sort_keys=True)

    if is_error:
        audit_logger.error(message)
    else:
        audit_logger.info(message)


app = FastAPI(
    title="Governed AP — Read-only PDF Intake",
    description=(
        "Document assessment only. No trusted ERP lookup, "
        "payment authorization, or payment execution."
    ),
    version="0.1.0",
)


# Allow the 15 MB invoice plus limited multipart framing overhead.
MAX_HTTP_BODY_BYTES = MAX_PDF_BYTES + 65_536

app.add_middleware(
    RequestBodyLimitMiddleware,
    max_body_size=MAX_HTTP_BODY_BYTES,
)


@app.middleware("http")
async def trace_request(request: Request, call_next):
    """Generate a server-controlled ID and log each HTTP request."""

    request_id = uuid4().hex
    request.state.request_id = request_id

    started = perf_counter()

    route = {
        "/health": "health",
        "/v1/invoices/assess": "invoice_assessment",
    }.get(request.url.path, "other")

    try:
        response = await call_next(request)

    except Exception:
        record_audit_event(
            "http_request",
            request_id,
            is_error=True,
            route=route,
            status_code=500,
        )
        raise

    response.headers["X-Request-ID"] = request_id

    elapsed_ms = round(
        (perf_counter() - started) * 1000,
        2,
    )

    record_audit_event(
        "http_request",
        request_id,
        route=route,
        status_code=response.status_code,
        duration_ms=elapsed_ms,
    )

    return response


# Limit expensive OCR processing in this single-process demonstration.
_assessment_slot = Lock()


# Read the caller's API key from the X-API-Key HTTP header.
_api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)


def require_api_key(
    supplied_key: Annotated[str | None, Security(_api_key_header)],
) -> None:
    """Reject unauthenticated requests and missing server configuration."""

    configured_key = os.environ.get("GOVERNED_AP_API_KEY", "")

    # Never allow missing or weak configuration to disable authentication.
    if len(configured_key) < 32:
        raise HTTPException(
            status_code=503,
            detail="Assessment authentication is not configured",
        )

    if supplied_key is None or not hmac.compare_digest(
        supplied_key.encode("utf-8"),
        configured_key.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )


class AssessmentResponse(BaseModel):
    """Explicitly prohibit autonomous approval at the HTTP boundary."""

    action: Literal["ESCALATE"] = "ESCALATE"
    human_review_required: Literal[True] = True
    payment_executed: Literal[False] = False
    governance_agent_invoked: Literal[False] = False
    source: Literal["NATIVE", "OCR", "ERROR"]
    reason_codes: list[str]
    extracted: PartialInvoice


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness only; does not assert OCR readiness."""
    return {"status": "ok", "mode": "read_only_document_intake"}


@app.post(
    "/v1/invoices/assess",
    response_model=AssessmentResponse,
    dependencies=[Depends(require_api_key)],
)
def assess_invoice(
    request: Request,
    file: Annotated[UploadFile, File(description="One PDF invoice")],
) -> AssessmentResponse:
    """Assess a PDF without constructing ERP facts or calling an LLM."""

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=415,
            detail="Only application/pdf is accepted",
        )

    try:
        # Read at most one byte beyond the maximum allowed PDF size.
        pdf_bytes = file.file.read(MAX_PDF_BYTES + 1)
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail="Could not read the upload",
        ) from error
    finally:
        file.file.close()

    if not pdf_bytes:
        raise HTTPException(
            status_code=400,
            detail="Empty PDF upload",
        )

    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail="PDF exceeds the 15 MB limit",
        )

    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=422,
            detail="Invalid PDF file signature",
        )

    if not _assessment_slot.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Assessment busy; retry later",
        )

    try:
        with TemporaryDirectory(prefix="governed-ap-") as folder:
            # Never trust the uploaded filename as a filesystem path.
            pdf_path = Path(folder) / "invoice.pdf"
            pdf_path.write_bytes(pdf_bytes)

            # Reuse the existing fail-closed intake module.
            # No trusted ERP context is supplied.
            result = assess_pdf(pdf_path)

    except Exception as error:
        # Unexpected processing failures must never become approvals.
        record_audit_event(
            "assessment_unavailable",
            request.state.request_id,
            is_error=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Assessment unavailable; human review required",
        ) from error

    finally:
        _assessment_slot.release()

    record_audit_event(
        "assessment_completed",
        request.state.request_id,
        source=result.source,
        reason_count=len(result.reason_codes),
        action="ESCALATE",
    )
    # Do not use result.action to authorize or execute payment.
    return AssessmentResponse(
        source=result.source,
        reason_codes=list(result.reason_codes),
        extracted=result.extracted,
    )
