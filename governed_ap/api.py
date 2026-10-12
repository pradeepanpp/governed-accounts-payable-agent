"""Local-only, read-only PDF invoice assessment HTTP interface."""

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from governed_ap.native_invoice_reader import MAX_PDF_BYTES, PartialInvoice
from governed_ap.pdf_intake import assess_pdf

app = FastAPI(
    title="Governed AP — Read-only PDF Intake",
    description=(
        "Document assessment only. No trusted ERP lookup, "
        "payment authorization, or payment execution."
    ),
    version="0.1.0",
)

# Limit expensive OCR processing in this single-process demonstration.
_assessment_slot = Lock()


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


@app.post("/v1/invoices/assess", response_model=AssessmentResponse)
def assess_invoice(
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
        raise HTTPException(
            status_code=503,
            detail="Assessment unavailable; human review required",
        ) from error

    finally:
        _assessment_slot.release()

    # Do not use result.action to authorize or execute payment.
    return AssessmentResponse(
        source=result.source,
        reason_codes=list(result.reason_codes),
        extracted=result.extracted,
    )
