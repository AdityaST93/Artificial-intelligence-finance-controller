"""
Razorpay AI Finance Controller - Streamlit entry point.

Razorpay-inspired design system, modular page architecture:
  - 8 pages: Dashboard, Reconciliation, Forecast, GST, Q&A, Exceptions, Audit, Settings
"""
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

# ============================================================================
# Page config (must be first)
# ============================================================================

st.set_page_config(
    page_title="Razorpay AI Finance Controller",
    page_icon="\U0001F4A0",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Built for Razorpay AI Buildathon \u00b7 Track 4 (AI Finance Controller) \u00b7 by Aditya Singh Thakur \u00b7 2026",
        "Get Help": "https://github.com/AdityaST93/Artificial-intelligence-finance-controller",
        "Report a bug": "https://github.com/AdityaST93/Artificial-intelligence-finance-controller/issues",
    },
)

# ============================================================================
# Design system + page imports
# ============================================================================

from ui import inject, hero, footer, PALETTE  # noqa: E402
from ui.pages import (  # noqa: E402
    dashboard, reconciliation, forecast, gst,
    qa, exceptions as exc_page, audit, settings,
)
from core.reconcile import run_reconciliation  # noqa: E402
from core.forecast import forecast_cash  # noqa: E402
from core.tax_match import match_gst  # noqa: E402
from core.exporter import export_excel, export_pdf_report  # noqa: E402

# Inject the design system CSS + counter runtime
inject()

# ============================================================================
# Hero banner
# ============================================================================

hero(
    "AI Finance Controller",
    "Multi-source reconciliation \u00b7 Settlement Q&A \u00b7 13-week cash forecast \u00b7 6-dimension GST match",
    chip="RAZORPAY AI BUILDATHON \u00b7 TRACK 4",
)

# ============================================================================
# Sidebar (controls only now - navigation moved to top tabs)
# ============================================================================

with st.sidebar:
    st.markdown("### \u2699\ufe0f Controls")
    st.caption("Configure and run the reconciliation engine.")

    default_key = os.getenv("OPENROUTER_API_KEY", "")
    api_key = st.text_input(
        "OpenRouter API Key",
        value=default_key if default_key else "",
        type="password",
        help="Free key at openrouter.ai/keys. Without it, the Q&A agent uses a deterministic fallback.",
    )
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key

    st.markdown("---")

    if st.button("\u25b6  Run Reconciliation", type="primary", use_container_width=True):
        with st.spinner("Reconciling 4 sources\u2026"):
            st.session_state["result"] = run_reconciliation()
            st.session_state["forecast"] = forecast_cash()
            st.session_state["gst"] = match_gst()
            st.success("\u2713 Reconciliation complete")

    if st.button("\U0001F5D1  Clear cache", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("**Stack**")
    st.caption("Streamlit \u00b7 LangChain \u00b7 pandas \u00b7 ChromaDB \u00b7 OpenRouter")
    st.markdown("**Dataset**")
    st.caption("60 payments \u00b7 58 credits \u00b7 61 orders \u00b7 58 invoices")
    st.markdown("---")
    st.caption("**Aditya Singh Thakur** \u00b7 2026")

# ============================================================================
# Data
# ============================================================================

result = st.session_state.get("result")
forecast_data = st.session_state.get("forecast")
gst_data = st.session_state.get("gst")

# ============================================================================
# Top tabs (navigation) - all 8 pages, always visible, no sidebar needed
# ============================================================================

if result is None:
    from ui import empty_state
    empty_state(
        "Welcome to your Finance Controller",
        "Hit \u25b6 Run Reconciliation in the sidebar to get started.",
    )
    st.markdown("---")
    if st.button("\u25b6  Run Reconciliation", type="primary", use_container_width=False):
        with st.spinner("Reconciling 4 sources\u2026"):
            st.session_state["result"] = run_reconciliation()
            st.session_state["forecast"] = forecast_cash()
            st.session_state["gst"] = match_gst()
            st.rerun()
else:
    with st.expander("\U0001F4E5  Download reconciliation report", expanded=False):
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                export_excel(result, tmp.name)
                excel_bytes = Path(tmp.name).read_bytes()
            st.download_button(
                "\U0001F4CA  Download Excel",
                data=excel_bytes,
                file_name="reconciliation.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with c2:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                export_pdf_report(result, tmp.name)
                pdf_bytes = Path(tmp.name).read_bytes()
            st.download_button(
                "\U0001F4C4  Download PDF",
                data=pdf_bytes,
                file_name="reconciliation.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with c3:
            st.caption(
                "Excel: 5 sheets (Summary, Matched, Exceptions, By Category, GST).  "
                "PDF: cover, exec summary with bar chart, exception details, audit trail."
            )

    st.markdown("---")

    tab_dashboard, tab_recon, tab_forecast, tab_gst, tab_qa, tab_exc, tab_audit, tab_settings = st.tabs([
        "\U0001F4CA Dashboard",
        "\U0001F517 Reconciliation",
        "\U0001F4B5 Forecast",
        "\U0001F9FE GST",
        "\U0001F4AC Q&A",
        "\u26A0\ufe0f Exceptions",
        "\U0001F50D Audit Trail",
        "\u2699\ufe0f Settings",
    ])

    with tab_dashboard:
        dashboard.render_dashboard(result)

    with tab_recon:
        reconciliation.render_reconciliation(result)

    with tab_forecast:
        if forecast_data is not None:
            forecast.render_forecast(forecast_data)
        else:
            st.info("Run reconciliation to see the forecast.")

    with tab_gst:
        if gst_data is not None:
            gst.render_gst(gst_data)
        else:
            st.info("Run reconciliation to see GST match.")

    with tab_qa:
        qa.render_qa()

    with tab_exc:
        exc_page.render_exceptions(result)

    with tab_audit:
        audit.render_audit(result)

    with tab_settings:
        settings.render_settings()

# ============================================================================
# Footer
# ============================================================================

footer()
