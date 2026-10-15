"""Local browser interface for review-only PDF assessment.

Run with: python -m streamlit run dashboard/app.py --server.address 127.0.0.1
The API key is read on this Python server, not included in browser JavaScript.
"""

import os

import streamlit as st

from dashboard.client import DashboardError, assess_invoice

st.set_page_config(page_title="Governed AP | Local Review", page_icon="📄", layout="wide")

st.title("Invoice Review Dashboard")
st.caption("Governed AP • local research demonstration • no payment functionality")
st.warning(
    "DEPLOYMENT HOLD: Fictional test invoices only. "
    "This interface does not verify ERP records, authorize payments, or execute payments."
)

api_key = os.environ.get("GOVERNED_AP_API_KEY", "")
if len(api_key) < 32:
    st.error(
        "Missing local API key. Set GOVERNED_AP_API_KEY before starting both "
        "the Docker API and this dashboard."
    )
    st.stop()

with st.form("invoice_upload_form"):
    uploaded = st.file_uploader(
        "Choose one fictional PDF invoice",
        type=["pdf"],
        accept_multiple_files=False,
        max_upload_size=15,
        help="The existing API enforces a strict 15,000,000-byte limit.",
    )
    submitted = st.form_submit_button("Assess fictional invoice", type="primary")

if submitted:
    st.session_state.pop("assessment_result", None)
    if uploaded is None:
        st.info("Select a fictional PDF first.")
    else:
        try:
            with st.spinner("Reading the PDF using the local assessment API..."):
                st.session_state["assessment_result"] = assess_invoice(uploaded.getvalue(), api_key)
        except DashboardError as error:
            st.error(str(error))

result = st.session_state.get("assessment_result")
if result is not None:
    decision, source, payment = st.columns(3)
    decision.metric("Decision", "ESCALATE")
    source.metric("Extraction source", result["source"])
    payment.metric("Payment executed", "NO")

    st.error("Human review required. This dashboard cannot approve or pay invoices.")

    st.subheader("Extracted fields (unverified)")
    labels = (
        ("invoice_number", "Invoice number"),
        ("invoice_date", "Invoice date"),
        ("currency", "Currency"),
        ("subtotal", "Subtotal"),
        ("tax", "Tax"),
        ("total", "Total"),
    )
    invoice = result["extracted"]
    st.table(
        [
            {"Field": label, "Extracted value": str(invoice.get(field) or "—")}
            for field, label in labels
        ]
    )

    st.subheader("Review reasons")
    explanations = {
        "TRUSTED_ERP_CONTEXT_MISSING": "Trusted purchase-order and receiving data are unavailable.",
        "REQUIRED_AP_FIELDS_UNVERIFIED": "Required invoice details have not been verified.",
        "DOCUMENT_INTAKE_FAILURE": "The document could not be processed reliably.",
    }
    if result["reason_codes"]:
        for code in result["reason_codes"]:
            st.text(f"{code} — {explanations.get(code, 'Manual review required.')}")
    else:
        st.write("Human review is required even when no specific reason code is provided.")

if result is not None and st.button("Clear displayed result"):
    st.session_state.pop("assessment_result", None)
    st.rerun()

st.caption(
    "Results exist only in the local dashboard session (not in a database). "
    "Use Clear displayed result when finished. Never upload real financial data."
)
