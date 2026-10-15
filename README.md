# Governed Accounts Payable AI Agent

**Governance-focused AI agent research for fictional accounts-payable decisions, with a separate read-only PDF invoice review dashboard.**

[![CI](https://github.com/pradeepanpp/governed-accounts-payable-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/pradeepanpp/governed-accounts-payable-agent/actions/workflows/ci.yml)
![Python 3.11](https://img.shields.io/badge/Python-3.11-blue)
![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-purple)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)
![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B)
![Docker](https://img.shields.io/badge/Container-Docker-2496ED)

> **Project status: Active research.** The experimental agent's fixed-mock development safety gate currently **fails**. The separate PDF review API always returns `ESCALATE`; it does not approve or execute payments. Public deployment is **on hold**.

## Overview

This repository studies a practical question in AI governance:

**How much does each protective layer reduce unsafe autonomous decisions, and how much automation, latency, and human-review effort does that protection cost?**

It contains **two deliberately separate systems**:

1. **Governed agent research workflow:** LangGraph orchestration over synthetic accounts-payable records, with deterministic checks, guardrails, history/policy checks, and a final enforcement gate. Outcomes such as `AUTO_APPROVE`, `ESCALATE`, and `BLOCK` are **simulated research decisions**, not real payments.
2. **Local invoice review application:** A Streamlit dashboard connected to an authenticated FastAPI endpoint. The endpoint extracts fields from fictional PDFs using native text extraction or offline Tesseract OCR, and always requires human review. It **does not call the LangGraph agent**, check live ERP records, or authorize a payment.

## Key features

- **Governance experiments:** Synthetic invoices and fictional ERP context, prompt-injection scenarios, deterministic policy checks, and safety/automation evaluation.
- **Conservative HTTP boundary:** The read-only assessment endpoint returns `ESCALATE`, requires human review, and reports `payment_executed: false`.
- **PDF intake:** Native text extraction with local OCR fallback, bounded document size/page count, and cumulative OCR time budget.
- **Local dashboard:** Upload a fictional PDF, inspect unverified invoice fields, view OCR/native extraction source, and read escalation reason codes.
- **Operational controls:** API-key authentication, request IDs, structured audit events, limited concurrent OCR assessments, and non-root Docker execution.
- **Automated verification:** pytest and Ruff checks, Docker/real-OCR CI integration tests, Trivy vulnerability reporting, a fixable-vulnerability policy, and a hardened-runtime CI demonstration.

## Architecture

**A. Experimental governance workflow (synthetic data only)**

```text
Fictional invoice + fictional purchase-order / receipt context
    -> Extraction and deterministic checks
    -> Guardrail, history and policy checks
    -> Agent recommendation
    -> Deterministic enforcement gate
    -> Simulated AUTO_APPROVE / ESCALATE / BLOCK
    -> Safety and automation evaluation
```

**B. Local read-only review application (separate from the research agent)**

```text
Browser -> Streamlit (127.0.0.1:8501)
              |
              v
          FastAPI (127.0.0.1:8000)
              -> PDF validation and bounded intake
              -> Native text or Tesseract OCR
              -> Extracted invoice fields (unverified)
              -> ESCALATE + human review required
              -> No ERP verification; no payment execution
```

## Development evaluation

The fixed-mock research benchmark contains **60 scenarios and 84 invoices**. Its development safety gate **failed**, including **4 unsafe approvals among 26 unsafe cases**. The mock guardrail always returned `flagged=false`; these figures **do not measure the effectiveness of a functioning LLM guardrail**.

| Development metric | Observed result |
| --- | ---: |
| Unsafe Action Rate (UAR) | 4/26 = **15.38%** |
| Benign Automation Coverage (BAC) | 37/37 = **100%** |
| Human Review Rate (HRR) | 29/84 = **34.52%** |
| Reported system failures | 0 |
| Development safety gate | **FAIL** |

See [Development Safety Findings](docs/DEVELOPMENT_SAFETY_FINDINGS.md) for the test conditions, known failures, and interpretation. **These are development-only mock-provider results, not independent safety certification or real-world financial performance.**

## Getting started — local fictional-invoice demonstration

**Requirements:** Docker Desktop, Python 3.11, Windows PowerShell, and a virtual environment. Run commands from the repository root. No paid LLM API is needed for this demonstration.

**1. Install dashboard dependencies** (in your activated Python virtual environment):

```powershell
python -m pip install -r requirements-dashboard.txt
```

**2. Start the local API container:**

```powershell
$env:GOVERNED_AP_API_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"

docker build -t governed-ap-assessment:local .

docker run --rm --detach --name governed-ap-local --cpus=1 --memory=1g --env GOVERNED_AP_API_KEY --publish 127.0.0.1:8000:8000 governed-ap-assessment:local

Invoke-RestMethod http://127.0.0.1:8000/health
```

**3. Start the Streamlit dashboard** in the same PowerShell environment:

```powershell
python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --server.maxUploadSize 15 --browser.gatherUsageStats false
```

Open **http://127.0.0.1:8501**. Upload the fictional fixture `tests/fixtures/ci_fictional_scanned_invoice.pdf` and run the assessment. The tested fixture produces invoice `TEST-2026-001`, currency `AED`, total `63.00`, extraction source `OCR`, and decision `ESCALATE`.

The API also provides local interactive documentation at **http://127.0.0.1:8000/docs**. Its `POST /v1/invoices/assess` endpoint requires an `X-API-Key` header.

**4. Stop the demonstration:** Press `Ctrl+C` in the Streamlit terminal, then run:

```powershell
docker stop governed-ap-local
Remove-Item Env:\GOVERNED_AP_API_KEY
```

See [Local Dashboard Guide](docs/LOCAL_DASHBOARD.md) for more information. Do **not** submit real or confidential financial documents.

## Run the tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
ruff format --check .
```

GitHub Actions runs the automated Python, Docker, security-scanning, and real-OCR integration checks. A successful CI run does **not** certify the governed research workflow safe for payment authorization.

## Security and limitations

- **Not a production payment system.** The API cannot verify live ERP facts, approve invoices, or move money. The dashboard displays assessment results; it is **not** an operational human-approval queue.
- **Fictional data only.** The local dashboard and API must not be made publicly accessible or used with real customer invoices.
- **OCR scope:** English and Arabic Tesseract resources are installed, but accurate multilingual invoice-field extraction has **not** been established across layouts or languages.
- **Residual container risks:** The documented Trivy baseline includes unresolved operating-system findings. The fixable-vulnerability CI gate and hardened-container test do **not** mean all vulnerabilities are resolved.
- **Deployment decision: HOLD.** No public Azure deployment is approved. See the [Container Security Risk Register](docs/CONTAINER_SECURITY_RISK_REGISTER.md) for remaining security-review requirements.

## Ongoing research and roadmap

| Area | Status |
| --- | --- |
| Governed LangGraph workflow and synthetic benchmark | **Implemented; research evaluation ongoing** |
| Fixed-mock development safety assessment | **Completed; safety gate FAILED** |
| Local PDF/OCR assessment API and Streamlit dashboard | **Implemented and locally tested** |
| Request tracing, OCR limits, Docker CI and security controls | **Implemented and CI-tested** |
| Working-guardrail evaluation, governance ablations, independent IID/OOD splits | **Planned research** |
| Azure architecture, deployment concepts and interview preparation | **Learning and planning stage; not deployed** |

The next research work will examine protective-layer ablations, false positives, reproducibility, and the safety-versus-automation trade-off. Azure deployment will be studied before implementation, and any eventual deployment is subject to a new security and cost-approval decision.

## Technology

Python 3.11 · LangGraph · Pydantic · FastAPI · Streamlit · Tesseract OCR · pypdf · pypdfium2 · Docker · pytest · Ruff · GitHub Actions · Trivy
