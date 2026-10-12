# Governed Accounts Payable AI Agent

[![CI](https://github.com/pradeepanpp/governed-accounts-payable-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/pradeepanpp/governed-accounts-payable-agent/actions/workflows/ci.yml)

A research-focused AI engineering project exploring how governance controls affect the safety and automation of accounts payable decisions. It combines an experimental agent workflow with a separate, read-only PDF assessment API.

## Project overview

The project has two distinct components:

- **Governed decision workflow:** A LangGraph-based research workflow using fictional accounts payable records to study policy checks, prompt-injection risks, human review, and governance-layer trade-offs.
- **Read-only PDF API:** A FastAPI service that extracts invoice fields from text-based or scanned PDFs using local Tesseract OCR. It always requires human review and never authorizes or executes payments.

**Research question:** How much does each governance layer reduce unsafe autonomous decisions, and what does it cost in automation, human review, latency, and model usage?

## System design

```text
Research workflow (synthetic data)
Invoice + fictional ERP context
    -> Extraction and deterministic checks
    -> Guardrail, history and policy checks
    -> Agent recommendation
    -> Deterministic enforcement gate
    -> Simulated AUTO_APPROVE / ESCALATE / BLOCK

Read-only API (separate from the agent)
Uploaded PDF
    -> Native text extraction or local OCR
    -> Invoice field extraction
    -> ESCALATE + human review required
```

The HTTP API does **not** invoke the LangGraph decision agent, verify ERP records, or initiate payments.

## Run the PDF API locally

**Requirements:** Docker Desktop and Windows PowerShell.

```powershell
docker build -t governed-ap-assessment:local .

$env:GOVERNED_AP_API_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"

docker run --rm --detach --name governed-ap-local --cpus=1 --memory=1g --env GOVERNED_AP_API_KEY --publish 127.0.0.1:8000:8000 governed-ap-assessment:local
```

Check the service:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Open **http://127.0.0.1:8000/docs** to submit a fictional invoice PDF through the interactive API documentation. Use the **Authorize** control to supply the key from `GOVERNED_AP_API_KEY`.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Local service health check |
| `POST /v1/invoices/assess` | Authenticated PDF intake and review-only assessment |

The assessment endpoint requires the `X-API-Key` header. Missing or incorrect client credentials return HTTP `401`; missing or weak server key configuration returns HTTP `503`. PDF uploads are limited to 15 MB, with an additional HTTP body-size limit.

Stop the container:

```powershell
docker stop governed-ap-local
```

Keep API keys, real invoices, and sensitive financial information out of Git.

## Run the tests

With Python 3.11+ and a virtual environment activated:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
ruff format --check .
```

GitHub Actions also runs Python checks and a Docker smoke test.

## Safety results and limitations

**The research workflow has not passed its development safety gate.** In a fixed mock-provider benchmark of 60 scenarios and 84 invoices, 4 of 26 unsafe cases resulted in unsafe approvals. These results do not measure the performance of a functioning LLM guardrail. See [Development Safety Findings](docs/DEVELOPMENT_SAFETY_FINDINGS.md).

The PDF API is deliberately narrower: it always returns `ESCALATE`, requires human review, and performs no payment operations. Local tests confirmed native-text extraction and OCR on fictional invoices; they do not establish OCR accuracy across real-world layouts or languages. The Docker image includes English and Arabic OCR resources, but multilingual accuracy has not been established.

This is a **local research and portfolio prototype**, not a production payment system. Public deployment would require additional security controls, including HTTPS, managed secrets, access policies, monitoring, and a formal security review.

## Technology

Python · LangGraph · FastAPI · Pydantic · Tesseract OCR · Docker · pytest · Ruff · GitHub Actions