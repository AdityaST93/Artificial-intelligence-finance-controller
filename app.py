"""
Razorpay AI Finance Controller - Streamlit entry point.

Razorpay-inspired design system, modular page architecture:
  - 8 pages: Dashboard, Reconciliation, Forecast, GST, Q&A, Exceptions, Audit, Settings
"""
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

# ============================================================================
# Page config (must be first)
# ============================================================================

st.set_page_config(
    page_title="Razorpay AI Finance Controller",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "Built for Razorpay AI Buildathon · Track 4 (AI Finance Controller) · by Aditya Singh Thakur · 2026",
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
    "Multi-source reconciliation · Settlement Q&A · 13-week cash forecast · 6-dimension GST match",
    chip="RAZORPAY AI BUILDATHON · TRACK 4",
)

# ============================================================================
# Sidebar
# ============================================================================

with st.sidebar:
    st.markdown("### ⚙️ Controls")
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

    if st.button("▶  Run Reconciliation", type="primary", use_container_width=True):
        with st.spinner("Reconciling 4 sources…"):
            st.session_state["result"] = run_reconciliation()
            st.session_state["forecast"] = forecast_cash()
            st.session_state["gst"] = match_gst()
            st.success("✓ Reconciliation complete")

    if st.button("🗑  Clear cache", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("**Stack**")
    st.caption("Streamlit · LangChain · pandas · ChromaDB · OpenRouter")
    st.markdown("**Dataset**")
    st.caption("60 payments · 58 credits · 61 orders · 58 invoices")

# ============================================================================
# Navigation
# ============================================================================

result = st.session_state.get("result")
forecast = st.session_state.get("forecast")
gst = st.session_state.get("gst")

# Sidebar navigation
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🧭 Navigate")
    page = st.radio(
        "Go to:",
        options=[
            "📊  Dashboard",
            "🔗  Reconciliation",
            "💵  Forecast",
            "🧾  GST",
            "💬  Q&A",
            "⚠️  Exceptions",
            "🔍  Audit Trail",
            "⚙️  Settings",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("**Aditya Singh Thakur** · 2026")

# ============================================================================
# Page dispatch
# ============================================================================

if result is None:
    from ui import empty_state
    empty_state(
        "Welcome to your Finance Controller",
        "Hit ▶ Run Reconciliation in the sidebar to get started.",
    )
    st.markdown("---")
    if st.button("▶  Run Reconciliation", type="primary", use_container_width=False):
        with st.spinner("Reconciling 4 sources…"):
            st.session_state["result"] = run_reconciliation()
            st.session_state["forecast"] = forecast_cash()
            st.session_state["gst"] = match_gst()
            st.rerun()
else:
    with st.expander("📥  Download reconciliation report", expanded=False):
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            excel_bytes = export_excel(result).getvalue()
            st.download_button(
                "📊  Download Excel",
                data=excel_bytes,
                file_name="reconciliation.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with c2:
            pdf_bytes = export_pdf_report(result).getvalue()
            st.download_button(
                "📄  Download PDF",
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

    if page.startswith("📊"):
        dashboard.render_dashboard(result)
    elif page.startswith("🔗"):
        reconciliation.render_reconciliation(result)
    elif page.startswith("💵"):
        if forecast is not None:
            forecast.render_forecast(forecast)
        else:
            st.info("Run reconciliation to see the forecast.")
    elif page.startswith("🧾"):
        if gst is not None:
            gst.render_gst(gst)
        else:
            st.info("Run reconciliation to see GST match.")
    elif page.startswith("💬"):
        qa.render_qa()
    elif page.startswith("⚠️"):
        exc_page.render_exceptions(result)
    elif page.startswith("🔍"):
        audit.render_audit(result)
    elif page.startswith("⚙️"):
        settings.render_settings()

# ============================================================================
# Footer
# ============================================================================

footer()
