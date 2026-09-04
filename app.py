"""
Razorpay AI Finance Controller - Streamlit entry point.

Razorpay-inspired design system, modular page architecture:
  - 8 pages: Dashboard, Reconciliation, Forecast, GST, Q&A, Exceptions, Audit, Settings
  - Sidebar: API key + Run button + Razorpay connection + PDF upload
  - Onboarding empty state when no result is loaded
  - Excel + PDF download after reconciliation

Public URL (Streamlit Cloud): https://<your-app>.streamlit.app
"""
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import streamlit as st

# Design system ----------------------------------------------------------
from ui.design_system import (
    CUSTOM_CSS,
    PALETTE,
    kpi_card,
    hero,
    footer,
    style_plotly,
    section_header,
    empty_state,
)

# Page modules -----------------------------------------------------------
from ui.pages.dashboard import render_dashboard
from ui.pages.reconciliation import render_reconciliation
from ui.pages.forecast import render_forecast
from ui.pages.gst import render_gst
from ui.pages.qa import render_qa
from ui.pages.exceptions import render_exceptions
from ui.pages.audit import render_audit
from ui.pages.settings import render_settings

# Components -------------------------------------------------------------
from ui.components import (
    razorpay_connection_section,
    pdf_upload_section,
    agent_response_card,
)

# Core engine (reconciliation / forecast / GST / export) -----------------
from core.reconcile import run_reconciliation
from core.forecast import forecast_cash
from core.tax_match import match_gst
from core.exporter import export_excel, export_pdf_report


# ============================================================================
# Page config (must be first Streamlit call)
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

# Inject the design-system CSS once per page load.
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ============================================================================
# Small helpers
# ============================================================================

def _safe_metrics(result) -> dict:
    """Return result.metrics as a dict, or empty dict."""
    if result is None:
        return {}
    m = getattr(result, "metrics", None)
    return m if isinstance(m, dict) else {}


def _decimal_ratio(r: float) -> Decimal:
    """Wrap a float into a Decimal (used for tone thresholds in forecast)."""
    return Decimal(str(r))


def _export_to_bytes(result) -> tuple[bytes | None, bytes | None]:
    """Render Excel + PDF exports to in-memory bytes.

    The exporter writes to disk; we use a tmp file under the system temp dir
    and read it back. Errors are returned as (None, None) so the UI degrades
    gracefully.
    """
    import tempfile

    excel_bytes: bytes | None = None
    pdf_bytes: bytes | None = None

    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            tmp_xlsx = Path(f.name)
        export_excel(result, tmp_xlsx)
        excel_bytes = tmp_xlsx.read_bytes()
        try:
            tmp_xlsx.unlink()
        except OSError:
            pass
    except Exception as e:  # pragma: no cover - defensive
        st.warning(f"Excel export failed: {e}")

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_pdf = Path(f.name)
        export_pdf_report(result, tmp_pdf)
        pdf_bytes = tmp_pdf.read_bytes()
        try:
            tmp_pdf.unlink()
        except OSError:
            pass
    except Exception as e:  # pragma: no cover - defensive
        st.warning(f"PDF export failed: {e}")

    return excel_bytes, pdf_bytes


# ============================================================================
# Hero
# ============================================================================

hero(
    "AI Finance Controller",
    "Multi-source reconciliation · Settlement Q&A · 13-week cash forecast · 6-dimension GST match",
)


# ============================================================================
# Sidebar - controls + navigation
# ============================================================================

with st.sidebar:
    st.markdown("### ⚙️  Controls")
    st.caption("Configure and run the reconciliation engine.")

    default_key = os.getenv("OPENROUTER_API_KEY", "")
    api_key = st.text_input(
        "OpenRouter API Key",
        value=default_key or "",
        type="password",
        help="Free key at openrouter.ai/keys. Without it, the Q&A agent uses a deterministic fallback.",
    )
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key
        st.session_state["openrouter_api_key"] = api_key

    st.markdown("---")

    run_clicked = st.button(
        "▶  Run Reconciliation",
        type="primary",
        use_container_width=True,
        key="run_reconciliation",
    )
    if run_clicked:
        with st.spinner("Reconciling 4 sources…"):
            try:
                result = run_reconciliation()
            except Exception as e:
                st.error(f"Reconciliation failed: {e}")
                result = None
            try:
                forecast = forecast_cash() if result is not None else None
            except Exception as e:
                st.warning(f"Forecast skipped: {e}")
                forecast = None
            try:
                gst = match_gst() if result is not None else None
            except Exception as e:
                st.warning(f"GST match skipped: {e}")
                gst = None

            st.session_state["result"] = result
            st.session_state["forecast"] = forecast
            st.session_state["gst"] = gst
            if result is not None:
                st.success("✓ Reconciliation complete")
            st.rerun()

    if st.button("🗑  Clear cache", use_container_width=True, key="clear_cache"):
        st.session_state.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("**Navigation**")

    # Settings lives behind a deep link in the sidebar.
    if st.button("⚙️  Open Settings", use_container_width=True, key="open_settings"):
        st.session_state["nav_page"] = "Settings"
        st.rerun()

    st.markdown("---")
    st.markdown("**Stack**")
    st.caption("Streamlit · LangChain 1.x · pandas · ChromaDB · OpenRouter")
    st.markdown("---")
    st.markdown("**Dataset**")
    st.caption("60 payments · 58 credits · 61 orders · 58 invoices · 9 seeded exceptions")

    # Optional Razorpay / PDF sections (collapsible) -----------------------
    with st.expander("🔌  Razorpay API", expanded=False):
        try:
            razorpay_connection_section()
        except Exception as e:  # pragma: no cover - defensive
            st.caption(f"Razorpay section unavailable: {e}")

    with st.expander("📄  PDF ingest", expanded=False):
        try:
            pdf_upload_section()
        except Exception as e:  # pragma: no cover - defensive
            st.caption(f"PDF section unavailable: {e}")


# ============================================================================
# Navigation
# ============================================================================

PAGES = [
    "Dashboard",
    "Reconciliation",
    "Forecast",
    "GST",
    "Q&A",
    "Exceptions",
    "Audit",
    "Settings",
]

# Default to Dashboard on first load.
if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "Dashboard"

# Tabbed navigation: 8 tabs across the top.
current = st.session_state["nav_page"]
try:
    selected_index = PAGES.index(current)
except ValueError:
    selected_index = 0

tab_labels = [
    "📊  Dashboard",
    "🔗  Reconciliation",
    "💵  Forecast",
    "🧾  GST",
    "💬  Q&A",
    "⚠️  Exceptions",
    "🛡  Audit",
    "⚙️  Settings",
]
tabs = st.tabs(tab_labels)
for i, page_name in enumerate(PAGES):
    pass  # tabs are referenced by index below

# Pull result objects out of session_state once.
result = st.session_state.get("result")
forecast = st.session_state.get("forecast")
gst = st.session_state.get("gst")


# ============================================================================
# Render the selected page
# ============================================================================

# Tab 1: Dashboard
with tabs[0]:
    if result is None:
        empty_state(
            title="Welcome 👋",
            subtitle=(
                "This dashboard closes the finance-ops loop for an Indian merchant "
                "on Razorpay — reconciliation, settlement Q&A, cash forecasting, and "
                "GST line matching, all in one place. Hit ▶ Run Reconciliation in "
                "the sidebar to get started."
            ),
        )

        # Top-level stats while no data is loaded
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                kpi_card("Match rate", "85%", "Tier-1 deterministic", tone="green"),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                kpi_card("Holdout F1", "1.00", "55 broken records", tone="green"),
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                kpi_card("Test coverage", "33/33", "pytest passing", tone="green"),
                unsafe_allow_html=True,
            )
    else:
        render_dashboard(result)

# Tab 2: Reconciliation
with tabs[1]:
    if result is None:
        st.info("Run reconciliation in the sidebar first.")
    else:
        render_reconciliation(result)

        # Download buttons (PDF + Excel)
        st.markdown("---")
        section_header(
            "Download reconciliation report",
            subtitle="Excel (5 sheets) and PDF (cover + summary + exception details).",
        )
        excel_bytes, pdf_bytes = _export_to_bytes(result)
        ts_label = pd.Timestamp.now().strftime("%Y%m%d_%H%M")
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if excel_bytes is not None:
                st.download_button(
                    "📊  Download Excel",
                    data=excel_bytes,
                    file_name=f"reconciliation_{ts_label}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="dl_excel",
                )
            else:
                st.caption("Excel export unavailable.")
        with c2:
            if pdf_bytes is not None:
                st.download_button(
                    "📄  Download PDF",
                    data=pdf_bytes,
                    file_name=f"reconciliation_{ts_label}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="dl_pdf",
                )
            else:
                st.caption("PDF export unavailable.")
        with c3:
            st.caption(
                "Excel: 5 sheets (Summary, Matched, Exceptions, By Category, GST).  "
                "PDF: cover, exec summary with bar chart, exception details, audit trail."
            )

# Tab 3: Forecast
with tabs[2]:
    if forecast is None:
        st.info("Run reconciliation to see the forecast.")
    else:
        render_forecast(forecast)

# Tab 4: GST
with tabs[3]:
    if gst is None:
        st.info("Run reconciliation to see GST match.")
    else:
        render_gst(gst)

# Tab 5: Q&A
with tabs[4]:
    if result is None:
        st.info("Run reconciliation first, then ask questions about your data.")
    else:
        render_qa(result)

# Tab 6: Exceptions
with tabs[5]:
    if result is None:
        st.info("Run reconciliation to see exceptions.")
    else:
        render_exceptions(result)

# Tab 7: Audit
with tabs[6]:
    if result is None:
        st.info("Run reconciliation to inspect the audit trail.")
    else:
        render_audit(result)

# Tab 8: Settings
with tabs[7]:
    render_settings()


# ============================================================================
# Footer
# ============================================================================

footer()
