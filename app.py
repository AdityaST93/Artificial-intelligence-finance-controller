"""
Razorpay AI Finance Controller — Streamlit entry point.

Razorpay-inspired design system:
  - Deep navy + electric blue gradient
  - Glassmorphism cards with subtle borders
  - Generous spacing, refined typography
  - Custom Plotly theme to match

Public URL (Streamlit Cloud): https://<your-app>.streamlit.app
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.reconcile import run_reconciliation
from core.forecast import forecast_cash
from core.tax_match import match_gst
from core.exporter import export_excel, export_pdf_report

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
# Design system — Razorpay-inspired
# ============================================================================

PALETTE = {
    "navy": "#0a2540",       # primary background
    "blue": "#3395ff",       # accent
    "cyan": "#00d4ff",       # secondary accent
    "green": "#10b981",      # success
    "amber": "#f59e0b",      # warning
    "red": "#ef4444",        # error
    "slate_900": "#0f172a",
    "slate_700": "#334155",
    "slate_500": "#64748b",
    "slate_300": "#cbd5e1",
    "slate_100": "#f1f5f9",
    "white": "#ffffff",
    "glass": "rgba(255, 255, 255, 0.05)",
    "glass_border": "rgba(255, 255, 255, 0.12)",
}

PLOTLY_THEME = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "Inter, system-ui, sans-serif", "color": "#0f172a"},
    "colorway": [PALETTE["blue"], PALETTE["cyan"], PALETTE["green"],
                 PALETTE["amber"], PALETTE["red"], "#8b5cf6", "#ec4899"],
    "margin": {"l": 24, "r": 24, "t": 48, "b": 24},
}

CUSTOM_CSS = """
<style>
  /* ---------- Root + typography ---------- */
  :root {
    --rp-navy: #0a2540;
    --rp-navy-2: #0e3a66;
    --rp-blue: #3395ff;
    --rp-cyan: #00d4ff;
    --rp-green: #10b981;
    --rp-amber: #f59e0b;
    --rp-red: #ef4444;
    --rp-slate-900: #0f172a;
    --rp-slate-700: #334155;
    --rp-slate-500: #64748b;
    --rp-slate-300: #cbd5e1;
    --rp-slate-100: #f1f5f9;
    --rp-glass: rgba(255, 255, 255, 0.04);
    --rp-glass-border: rgba(255, 255, 255, 0.10);
  }

  html, body, [data-testid="stAppViewContainer"] {
    background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%) !important;
    color: var(--rp-slate-900);
    font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  }

  /* Hide Streamlit chrome */
  #MainMenu, footer, header [data-testid="stToolbar"] { visibility: hidden; }
  [data-testid="stDecoration"] { display: none; }

  /* ---------- Hero ---------- */
  .rp-hero {
    background:
      radial-gradient(1200px 400px at 80% 0%, rgba(51, 149, 255, 0.18), transparent 60%),
      radial-gradient(900px 300px at 0% 100%, rgba(0, 212, 255, 0.12), transparent 60%),
      linear-gradient(135deg, #0a2540 0%, #0e3a66 100%);
    color: #fff;
    padding: 2.4rem 2.6rem 2.6rem 2.6rem;
    border-radius: 22px;
    margin-bottom: 1.4rem;
    box-shadow: 0 20px 60px -20px rgba(10, 37, 64, 0.45);
    position: relative;
    overflow: hidden;
  }
  .rp-hero::after {
    content: "";
    position: absolute; inset: 0;
    background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='60' height='60' viewBox='0 0 60 60'><circle cx='1' cy='1' r='1' fill='%23ffffff' fill-opacity='0.05'/></svg>");
    pointer-events: none;
  }
  .rp-hero h1 {
    font-size: 2.1rem; font-weight: 800; margin: 0 0 .35rem 0;
    background: linear-gradient(90deg, #fff 0%, #00d4ff 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    letter-spacing: -0.02em;
  }
  .rp-hero p { color: rgba(255,255,255,0.78); margin: 0; font-size: 0.98rem; }
  .rp-hero .rp-chip {
    display: inline-block; padding: 4px 12px; border-radius: 999px;
    background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.18);
    color: #cbd5e1; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.04em;
    text-transform: uppercase; margin-bottom: 0.8rem;
  }

  /* ---------- Sidebar ---------- */
  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0a2540 0%, #0e3a66 100%) !important;
    color: #fff;
  }
  [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
  [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4 {
    color: #fff !important; font-weight: 700;
  }
  [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.10) !important; }
  [data-testid="stSidebar"] .stMarkdown small { color: #94a3b8 !important; }

  /* Sidebar input */
  [data-testid="stSidebar"] input[type="password"],
  [data-testid="stSidebar"] input[type="text"] {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    color: #fff !important;
  }
  [data-testid="stSidebar"] label { color: #cbd5e1 !important; }

  /* ---------- Buttons ---------- */
  .stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em;
    transition: transform .12s ease, box-shadow .12s ease;
  }
  .stButton > button:hover { transform: translateY(-1px); }

  /* Primary button (Run Reconciliation) */
  [data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #3395ff 0%, #00d4ff 100%) !important;
    color: #0a2540 !important;
    border: none !important;
    box-shadow: 0 6px 20px -6px rgba(51, 149, 255, 0.6);
  }
  [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    box-shadow: 0 10px 30px -8px rgba(51, 149, 255, 0.8);
  }

  /* ---------- KPI cards ---------- */
  .rp-kpi {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    padding: 1.1rem 1.2rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    transition: transform .15s ease, box-shadow .15s ease;
    position: relative;
    overflow: hidden;
  }
  .rp-kpi:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 30px -12px rgba(15, 23, 42, 0.18);
  }
  .rp-kpi::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, var(--rp-blue) 0%, var(--rp-cyan) 100%);
  }
  .rp-kpi .label { color: #64748b; font-size: 0.78rem; font-weight: 600;
                   text-transform: uppercase; letter-spacing: 0.06em; }
  .rp-kpi .value { color: #0f172a; font-size: 1.85rem; font-weight: 800;
                   letter-spacing: -0.02em; margin-top: 0.2rem; }
  .rp-kpi .delta { color: #10b981; font-size: 0.82rem; font-weight: 600; margin-top: 0.25rem; }
  .rp-kpi.amber::before { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
  .rp-kpi.red::before { background: linear-gradient(90deg, #ef4444, #f87171); }
  .rp-kpi.green::before { background: linear-gradient(90deg, #10b981, #34d399); }

  /* ---------- Tabs ---------- */
  .stTabs [data-baseweb="tab-list"] {
    gap: 4px; background: transparent; padding: 0;
    border-bottom: 1px solid #e2e8f0;
  }
  .stTabs [data-baseweb="tab"] {
    background: transparent; border-radius: 8px 8px 0 0;
    padding: 12px 20px; font-weight: 600; color: #64748b;
    border: none;
  }
  .stTabs [aria-selected="true"] {
    color: #0a2540 !important;
    border-bottom: 3px solid #3395ff !important;
    background: transparent !important;
  }
  .stTabs [data-baseweb="tab"]:hover { color: #0a2540; }

  /* ---------- Subheaders ---------- */
  h2, h3 { color: #0f172a !important; font-weight: 700 !important; letter-spacing: -0.01em; }
  .stCaption, [data-testid="stCaptionContainer"] { color: #64748b !important; }

  /* ---------- DataFrames ---------- */
  .stDataFrame {
    border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  }

  /* ---------- Alert / warning ---------- */
  .stAlert {
    border-radius: 12px !important;
    border: 1px solid #fde68a !important;
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%) !important;
  }

  /* ---------- Chat ---------- */
  [data-testid="stChatMessage"] {
    background: #fff; border: 1px solid #e2e8f0; border-radius: 14px;
    padding: 1rem 1.2rem; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  }
  [data-testid="stChatMessage"][data-testid*="user"] {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border-color: #bae6fd;
  }

  /* ---------- Download buttons ---------- */
  .stDownloadButton > button {
    background: linear-gradient(135deg, #3395ff 0%, #00d4ff 100%) !important;
    color: #0a2540 !important; border: none !important; font-weight: 700 !important;
    box-shadow: 0 6px 18px -6px rgba(51, 149, 255, 0.5);
  }
  .stDownloadButton > button:hover {
    box-shadow: 0 10px 28px -8px rgba(51, 149, 255, 0.7) !important;
  }

  /* ---------- Footer ---------- */
  .rp-footer {
    text-align: center; color: #64748b; font-size: 0.85rem;
    padding: 2rem 0 1rem 0; margin-top: 2rem;
    border-top: 1px solid #e2e8f0;
  }
  .rp-footer a { color: #3395ff; text-decoration: none; font-weight: 600; }
  .rp-footer a:hover { text-decoration: underline; }

  /* ---------- Hero metric row ---------- */
  .rp-hero-metric {
    display: inline-block; padding: 8px 16px; margin: 8px 8px 0 0;
    background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.18);
    border-radius: 10px; color: #fff; backdrop-filter: blur(8px);
  }
  .rp-hero-metric .v { font-size: 1.3rem; font-weight: 800; color: #00d4ff; }
  .rp-hero-metric .l { font-size: 0.72rem; color: #cbd5e1; text-transform: uppercase;
                       letter-spacing: 0.06em; font-weight: 600; }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ============================================================================
# Reusable UI components
# ============================================================================

def kpi_card(label: str, value: str, delta: str = "", tone: str = "default") -> str:
    """Render a KPI card as HTML (immune to Streamlit column padding)."""
    cls = "rp-kpi"
    if tone in ("amber", "red", "green"):
        cls += f" {tone}"
    delta_html = f'<div class="delta">{delta}</div>' if delta else ""
    return f"""
    <div class="{cls}">
      <div class="label">{label}</div>
      <div class="value">{value}</div>
      {delta_html}
    </div>
    """


def hero(title: str, subtitle: str, chip: str = "TRACK 4 · AI FINANCE CONTROLLER") -> None:
    """Render the gradient hero banner."""
    st.markdown(
        f"""
        <div class="rp-hero">
          <div class="rp-chip">{chip}</div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def footer() -> None:
    """Render the page footer with branding."""
    st.markdown(
        """
        <div class="rp-footer">
          Built for <a href="https://razorpay.com/buildathon/" target="_blank">Razorpay AI Buildathon</a>
          · Track 4 (AI Finance Controller) · by
          <a href="https://github.com/AdityaST93" target="_blank">Aditya Singh Thakur</a>
          · <a href="https://github.com/AdityaST93/Artificial-intelligence-finance-controller" target="_blank">Source on GitHub</a>
          · MIT License
        </div>
        """,
        unsafe_allow_html=True,
    )


def style_plotly(fig) -> None:
    """Apply Razorpay-inspired theme to a Plotly figure."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, system-ui, sans-serif", "color": "#0f172a"},
        margin={"l": 24, "r": 24, "t": 48, "b": 24},
    )


# ============================================================================
# Header (hero)
# ============================================================================

hero(
    "AI Finance Controller",
    "Multi-source reconciliation · Settlement Q&A · 13-week cash forecast · 6-dimension GST match",
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
            result = run_reconciliation()
            forecast = forecast_cash()
            gst = match_gst()
            st.session_state["result"] = result
            st.session_state["forecast"] = forecast
            st.session_state["gst"] = gst
            st.success("✓ Reconciliation complete")

    if st.button("🗑  Clear cache", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("**Stack**")
    st.caption("Streamlit · LangChain 1.x · pandas · ChromaDB · OpenRouter")
    st.markdown("---")
    st.markdown("**Dataset**")
    st.caption("60 payments · 58 credits · 61 orders · 58 invoices · 9 seeded exceptions")

# ============================================================================
# Main
# ============================================================================

result = st.session_state.get("result")
forecast = st.session_state.get("forecast")
gst = st.session_state.get("gst")

if result is None:
    # Empty state
    st.markdown("### Welcome 👋")
    st.markdown(
        """
        This dashboard closes the **finance-ops loop** for an Indian merchant running on Razorpay —
        reconciliation, settlement Q&A, cash forecasting, and GST line matching, all in one place.

        Hit **▶ Run Reconciliation** in the sidebar to get started. Then explore the tabs:

        | Tab | What you'll see |
        |---|---|
        | **📊 Reconciliation** | Match rate, exception breakdown, GST alignment |
        | **💵 Cash Forecast** | 13-week projection of opening → closing balance |
        | **🧾 GST Match** | 6-dimension line match · ITC claimed vs eligible |
        | **💬 Q&A Agent** | Ask in plain English, get cited answers |
        | **⚠️ Exceptions** | Every unresolvable record, named and categorised |

        > Built for the **Razorpay AI Buildathon · Track 4**. Every exception is honest,
        > every answer is cited, every rupee is Decimal-safe.
        """
    )

    # Feature highlights as cards
    cols = st.columns(3)
    with cols[0]:
        st.markdown(
            kpi_card("Match rate", "85%", "Tier-1 deterministic", tone="green"),
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            kpi_card("Holdout F1", "1.00", "55 broken records", tone="green"),
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            kpi_card("Test coverage", "33/33", "pytest passing", tone="green"),
            unsafe_allow_html=True,
        )

    footer()

else:
    m = result.metrics

    # ------------------------------------------------------------------
    # Top KPIs
    # ------------------------------------------------------------------
    match_rate_pct = m.get("match_rate", 0) * 100
    n_payments = m.get("razorpay_payments", 0)
    n_matched = m.get("tier1_matched_payments", 0)
    n_clean = m.get("clean_payments", 0)
    n_excs = m.get("tier1_exceptions", 0)
    n_bank = m.get("bank_credits", 0)
    n_gst = m.get("gst_invoices", 0)

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(
            kpi_card("Match rate", f"{match_rate_pct:.1f}%",
                     f"{n_clean}/{n_payments} clean", tone="green"),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            kpi_card("Payments", str(n_payments), f"{n_matched} matched"),
            unsafe_allow_html=True,
        )
    with k3:
        exc_tone = "amber" if 0 < n_excs < 10 else ("red" if n_excs >= 10 else "green")
        st.markdown(
            kpi_card("Exceptions", str(n_excs), "categorised", tone=exc_tone),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            kpi_card("Bank credits", str(n_bank), "verified"),
            unsafe_allow_html=True,
        )
    with k5:
        st.markdown(
            kpi_card("GST invoices", str(n_gst), "matched"),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.2rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Download reports
    # ------------------------------------------------------------------
    with st.expander("📥  Download reconciliation report", expanded=False):
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            excel_bytes = export_excel(result).getvalue()
            st.download_button(
                "📊  Download Excel",
                data=excel_bytes,
                file_name=f"reconciliation_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with c2:
            pdf_bytes = export_pdf_report(result).getvalue()
            st.download_button(
                "📄  Download PDF",
                data=pdf_bytes,
                file_name=f"reconciliation_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with c3:
            st.caption(
                "Excel: 5 sheets (Summary, Matched, Exceptions, By Category, GST).  "
                "PDF: cover, exec summary with bar chart, exception details, audit trail."
            )

    st.markdown("---")

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📊  Reconciliation", "💵  Cash Forecast",
         "🧾  GST Match", "💬  Q&A Agent", "⚠️  Exceptions"]
    )

    # ---- TAB 1: Reconciliation ----
    with tab1:
        st.subheader("Source comparison")
        st.caption("Each source feeds the reconciliation engine. Match rate is over Razorpay payments.")

        c1, c2, c3, c4 = st.columns(4)
        for col, label, val, sub in [
            (c1, "Razorpay", m.get("razorpay_payments", 0), "payments + refunds"),
            (c2, "Bank", m.get("bank_credits", 0), "settled credits"),
            (c3, "OMS", m.get("oms_orders", 0), "internal orders"),
            (c4, "GST", m.get("gst_invoices", 0), "tax invoices"),
        ]:
            with col:
                st.markdown(kpi_card(label, str(val), sub), unsafe_allow_html=True)

        st.markdown("### Tier-1 funnel")
        st.markdown(
            f"""
            - **Tier 1 (deterministic pandas):** joined Razorpay settlements against bank UTRs,
              OMS `transaction_id`s, and GST `razorpay_payment_id`s. {n_matched} payments got at
              least one match.
            - **Tier 2 (fuzzy, rapidfuzz):** reserved for residue — dates off by ±2 days,
              amounts within ±₹0.05 tolerance, fuzzy name match.
            - **Tier 3 (LLM, OpenRouter):** never on the happy path. Used only when both
              Tier 1 and Tier 2 fail, with a confidence gate ≥ 0.7.
            - **Below the gate:** {n_excs} honest exceptions, every one named and categorised.
            """
        )

        if gst is not None:
            st.markdown("### GST line match (6 dimensions)")
            gm = gst.metrics
            g1, g2, g3, g4 = st.columns(4)
            with g1:
                st.markdown(kpi_card("Invoices matched", str(gm["gst_matched"]), "all 6 dims"), unsafe_allow_html=True)
            with g2:
                st.markdown(kpi_card("Mismatches", str(gm["gst_mismatches"]), "flagged", tone="amber"), unsafe_allow_html=True)
            with g3:
                st.markdown(kpi_card("Missing invoices", str(gm["gst_missing"]), "to be generated", tone="amber"), unsafe_allow_html=True)
            with g4:
                st.markdown(
                    kpi_card("At-risk ITC", f"₹{gm['at_risk_itc']:,.2f}", "recoverable", tone="red"),
                    unsafe_allow_html=True,
                )

    # ---- TAB 2: Cash Forecast ----
    with tab2:
        if forecast is None:
            st.info("Run reconciliation to see the forecast.")
        else:
            st.subheader("13-week cash flow projection")
            st.caption("Deterministic projection from reconciled settlement history (net of fees + refunds).")

            f1, f2, f3, f4 = st.columns(4)
            with f1:
                st.markdown(kpi_card("Opening", f"₹{forecast.opening_balance:,.0f}", "today"), unsafe_allow_html=True)
            with f2:
                st.markdown(kpi_card("Closing", f"₹{forecast.closing_balance:,.0f}", f"in 13 weeks", tone="green"), unsafe_allow_html=True)
            with f3:
                tone = "red" if forecast.lowest_balance < forecast.opening_balance * Decimal_ratio(0.10) else "amber"
                st.markdown(kpi_card("Lowest", f"₹{forecast.lowest_balance:,.0f}", f"week {forecast.lowest_week}", tone=tone), unsafe_allow_html=True)
            with f4:
                net_delta = forecast.total_inflow - forecast.total_outflow
                st.markdown(kpi_card("Net Δ", f"₹{net_delta:,.0f}", "inflows − outflows", tone="green"), unsafe_allow_html=True)

            if forecast.alert:
                st.warning(f"⚠️  {forecast.alert}")

            # Chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=forecast.df["week"],
                y=forecast.df["closing"],
                mode="lines+markers",
                name="Closing balance",
                line=dict(color=PALETTE["blue"], width=3, shape="spline"),
                marker=dict(size=8, color=PALETTE["cyan"], line=dict(color=PALETTE["blue"], width=2)),
                fill="tozeroy",
                fillcolor="rgba(51, 149, 255, 0.10)",
                hovertemplate="<b>Week %{x}</b><br>Closing: ₹%{y:,.2f}<extra></extra>",
            ))
            fig.add_trace(go.Bar(
                x=forecast.df["week"],
                y=forecast.df["inflow"],
                name="Inflow",
                marker=dict(color="rgba(16, 185, 129, 0.6)"),
                hovertemplate="<b>Week %{x}</b><br>Inflow: ₹%{y:,.2f}<extra></extra>",
            ))
            fig.add_trace(go.Bar(
                x=forecast.df["week"],
                y=-forecast.df["outflow"],
                name="Outflow",
                marker=dict(color="rgba(239, 68, 68, 0.6)"),
                hovertemplate="<b>Week %{x}</b><br>Outflow: ₹%{y:,.2f}<extra></extra>",
            ))
            fig.update_layout(
                title=dict(text="<b>13-Week Cash Forecast</b>", x=0, font=dict(size=18)),
                xaxis=dict(title="Week", showgrid=False, zeroline=False),
                yaxis=dict(title="₹ (INR)", showgrid=True, gridcolor="rgba(15, 23, 42, 0.06)"),
                barmode="overlay",
                hovermode="x unified",
                height=500,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            style_plotly(fig)
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📋  Weekly details", expanded=False):
                st.dataframe(forecast.df, use_container_width=True, hide_index=True)

    # ---- TAB 3: GST Match ----
    with tab3:
        if gst is None:
            st.info("Run reconciliation to see GST match.")
        else:
            st.subheader("6-dimension GST line match")
            st.caption("Each Razorpay payment is checked against its GST invoice on GSTIN, invoice number, date, taxable value, tax breakup, and HSN.")

            gc1, gc2, gc3 = st.columns(3)
            with gc1:
                st.markdown(kpi_card("ITC claimed", f"₹{gst.itc_claimed:,.0f}", "eligible input credit"), unsafe_allow_html=True)
            with gc2:
                st.markdown(kpi_card("ITC eligible", f"₹{gst.itc_eligible:,.0f}", "post-match", tone="green"), unsafe_allow_html=True)
            with gc3:
                delta = gst.itc_eligible - gst.itc_claimed
                st.markdown(
                    kpi_card("At-risk ITC", f"₹{gst.at_risk_itc:,.2f}",
                             f"Δ ₹{delta:,.2f}", tone="red"),
                    unsafe_allow_html=True,
                )

            if not gst.mismatches.empty:
                st.markdown("### ❌ Mismatches")
                st.dataframe(
                    gst.mismatches[["payment_id", "invoice_no", "issues"]].head(20),
                    use_container_width=True, hide_index=True,
                )
            if not gst.missing_invoices.empty:
                st.markdown("### ⚠️ Missing GST invoices")
                st.dataframe(
                    gst.missing_invoices[["payment_id"]].head(20),
                    use_container_width=True, hide_index=True,
                )

    # ---- TAB 4: Q&A Agent ----
    with tab4:
        st.subheader("💬  Settlement Q&A Agent")
        st.caption("Ask in plain English. The agent cites source rows and shows the math.")

        # Suggested questions
        st.markdown("**Try asking:**")
        suggestions = [
            "Why is pay_S30006 short?",
            "Show reconciliation summary",
            "List all exceptions",
            "List missing_bank_credit exceptions",
            "Show fee variance",
        ]
        cols = st.columns(min(len(suggestions), 5))
        for i, q in enumerate(suggestions):
            with cols[i % len(cols)]:
                if st.button(q, key=f"sugg_{i}", use_container_width=True):
                    st.session_state["pending_q"] = q

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        pending = st.session_state.pop("pending_q", None)
        user_input = st.chat_input("Ask a finance question…")
        question = pending or user_input

        if question:
            st.session_state.chat_history.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    from core.agent import ask
                    answer = ask(question)
                    st.markdown(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})

    # ---- TAB 5: Exceptions ----
    with tab5:
        st.subheader("Exception taxonomy")
        st.caption("Every unresolved record is named. No silent drops.")

        cats = m.get("exception_categories", {})
        if cats:
            ca, cb = st.columns([1, 1])
            with ca:
                fig = px.pie(
                    values=list(cats.values()),
                    names=list(cats.keys()),
                    hole=0.55,
                    title="Exception breakdown",
                )
                fig.update_traces(textposition="inside", textinfo="percent+label",
                                  marker=dict(colors=[PALETTE["blue"], PALETTE["cyan"],
                                                       PALETTE["amber"], PALETTE["red"],
                                                       "#8b5cf6", "#ec4899", "#06b6d4",
                                                       "#84cc16", "#f97316"]))
                fig.update_layout(height=450, showlegend=False, title_font_size=18)
                style_plotly(fig)
                st.plotly_chart(fig, use_container_width=True)
            with cb:
                fig2 = px.bar(
                    x=list(cats.values()),
                    y=list(cats.keys()),
                    orientation="h",
                    title="Counts by category",
                    labels={"x": "Count", "y": "Category"},
                    color=list(cats.values()),
                    color_continuous_scale=["#3395ff", "#00d4ff"],
                )
                fig2.update_layout(height=450, yaxis=dict(autorange="reversed"),
                                   coloraxis_showscale=False, title_font_size=18)
                style_plotly(fig2)
                st.plotly_chart(fig2, use_container_width=True)

            st.markdown("---")
            st.markdown("### 📋 Exception details")
            st.dataframe(
                result.exceptions.fillna("—"),
                use_container_width=True, height=400,
            )
        else:
            st.success("✅ No exceptions — clean reconciliation.")

        with st.expander("📖  Exception taxonomy (10 categories)", expanded=False):
            st.markdown(
                """
                | Category | Trigger | Suggested action |
                |---|---|---|
                | `missing_bank_credit` | Razorpay settled, bank has no UTR | Wait 24h; raise with Razorpay support |
                | `orphan_bank_credit` | Bank credit, no Razorpay UTR | Investigate source; log to suspense ledger |
                | `amount_mismatch` | UTR matches, amount differs > ₹0.05 | Compare fee schedule; raise dispute |
                | `oms_amount_mismatch` | Razorpay ≠ OMS total | Reconcile cart; refund/adjust OMS |
                | `missing_oms_order` | Razorpay payment, no OMS | Investigate; possibly fraud |
                | `ghost_oms_order` | OMS paid, no Razorpay payment | Verify with customer; flag fraud |
                | `cancelled_order_with_payment` | OMS cancelled, Razorpay captured | Initiate refund via API |
                | `fee_rate_variance` | Razorpay fee ≠ contracted MDR | Update fee schedule; raise with AM |
                | `gst_amount_mismatch` | Invoice total ≠ Razorpay amount | Regenerate invoice; fix tax engine |
                | `missing_gst_invoice` | Payment, no GST invoice | Generate invoice; late-file if past |
                """
            )

    footer()


# ============================================================================
# Helper for tone in forecast tab
# ============================================================================

def Decimal_ratio(r: float):
    from decimal import Decimal
    return Decimal(str(r))
