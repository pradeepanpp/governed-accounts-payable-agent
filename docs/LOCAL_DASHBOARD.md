# Local invoice review dashboard (Improvement 5, first slice)

This local-only Streamlit frontend calls the **existing** authenticated FastAPI
`POST /v1/invoices/assess` endpoint. It is separate from the governed-agent
research workflow and cannot authorize or execute payments.

## Boundaries and limitations

- Fictional/synthetic invoices only. The API always returns `ESCALATE`.
- No cloud hosting or public sharing. The deployment HOLD in
  `docs/CONTAINER_SECURITY_RISK_REGISTER.md` still applies.
- The API key is read from the dashboard Python process environment and sent
  only to `http://127.0.0.1:8000`. It is **not hard-coded in frontend source**
  or inserted into client-side JavaScript.
- The dashboard does not persist invoices or responses to a database. Streamlit
  holds uploads/results in memory for a browser session; use the Clear button
  and stop the local processes after testing. Do not treat the interface as an
  access-control boundary for a public network.
- Actual limits and restrictions are enforced by the API; the browser file
  picker is not a security control. External PDF inputs are not approved.

## Run locally in Windows PowerShell

From the repository root with `.venv` activated:

```powershell
python -m pip install -r requirements-dashboard.txt
$env:GOVERNED_AP_API_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"

docker build -t governed-ap-assessment:dashboard .
docker run --rm -d --name governed-ap-local --env GOVERNED_AP_API_KEY --publish 127.0.0.1:8000:8000 governed-ap-assessment:dashboard
Invoke-RestMethod http://127.0.0.1:8000/health

python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --server.maxUploadSize 15 --browser.gatherUsageStats false
```

Open `http://127.0.0.1:8501` in a local browser, upload
`tests/fixtures/ci_fictional_scanned_invoice.pdf`, and click
**Assess fictional invoice**. Confirm source `OCR`, invoice
`TEST-2026-001`, total `63.00`, and `ESCALATE`.

In the Streamlit terminal press `Ctrl+C`, then clean up:

```powershell
docker rm -f governed-ap-local
Remove-Item Env:\GOVERNED_AP_API_KEY
```

If another service already uses port 8000, stop or investigate that service
instead of changing the dashboard URL to an arbitrary external host.

## Offline unit tests

```powershell
python -m pytest -q tests/test_dashboard.py
ruff check .
ruff format --check .
```

The dashboard client is tested with `httpx.MockTransport`, which does not
contact a real server or use an LLM/API credit.
