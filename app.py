"""
Razorpay AI Finance Controller — Streamlit entry point.

Run with:  streamlit run app.py
Public URL (Streamlit Cloud): https://[your-app].streamlit.app
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.reconcile import run_reconciliation
from core.forecast import forecast_cash
from core.tax_match import match_gst
from core.exporter import export_excel, export_pdf_report

st.set_page_config(
    page_title="Razorpay AI Finance Controller",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("💰 Razorpay AI Finance Controller")
st.markdown(
    "**Track 4** · Multi-source reconciliation · Settlement Q&A · "
    "Cash forecaster · GST matcher · Honest exception list"
)
st.caption("Built for Razorpay AI Buildathon · Aditya Singh Thakur · 2026")

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Controls")

    # OpenRouter key
    default_key = os.getenv("OPENROUTER_API_KEY", "")
    api_key = st.text_input(
        "OpenRouter API Key",
        value=default_key if default_key else "",
        type="password",
        help="Free key at openrouter.ai/keys. Without it, deterministic answers still work.",
    )
    if api_key:
        os.environ["OPENROUTER_API_KEY"] = api_key

    st.markdown("---")
    if st.button("🔄 Run Reconciliation", type="primary", use_container_width=True):
        with st.spinner("Reconciling 4 sources…"):
            result = run_reconciliation()
            forecast = forecast_cash()
            gst = match_gst()
            st.session_state["result"] = result
            st.session_state["forecast"] = forecast
            st.session_state["gst"] = gst
            st.success("Done!")

    if st.button("🗑️ Clear cache", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("**Stack:**")
    st.markdown("- Streamlit · LangChain · pandas")
    st.markdown("- OpenRouter (Llama 3.3 70B / Gemini Flash)")
    st.markdown("- Plotly · Decimal-safe math")
    st.markdown("---")
    st.markdown("**Sources:** 4 synthetic CSVs (60 + 58 + 61 + 59 rows)")
    st.markdown("**Seed:** 10 honest exceptions")

    # ------------------------------------------------------------------
    # Razorpay test-mode API connection
    # ------------------------------------------------------------------
    st.markdown("---")
    st.header("🔌 Razorpay API Connection")
    st.caption(
        "Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in your environment "
        "to pull live data. Without them, the client falls back to synthetic data."
    )

    # Lazy import so the rest of the app starts even if requests is missing
    try:
        from core.razorpay_client import RazorpayClient

        rzp_client = RazorpayClient()
        ok, msg = rzp_client.test_connection()
        if ok:
            st.success(f"✅ {msg}")
        else:
            st.warning(f"⚠️ {msg}")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("💳 Pull latest payments", use_container_width=True):
                with st.spinner("Calling GET /v1/payments…"):
                    try:
                        payments_df = rzp_client.list_payments(count=50)
                        st.session_state["rzp_payments"] = payments_df
                        st.success(f"Pulled {len(payments_df)} payment rows")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Failed: {exc}")
        with col_b:
            if st.button("🏦 Pull latest settlements", use_container_width=True):
                with st.spinner("Calling GET /v1/settlements…"):
                    try:
                        settlements_df = rzp_client.list_settlements(count=50)
                        st.session_state["rzp_settlements"] = settlements_df
                        st.success(f"Pulled {len(settlements_df)} settlement rows")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Failed: {exc}")

        # Show pulled data if available
        if "rzp_payments" in st.session_state:
            with st.expander("💳 Latest payments (from API)", expanded=False):
                st.dataframe(
                    st.session_state["rzp_payments"].head(50),
                    use_container_width=True,
                    hide_index=True,
                )
        if "rzp_settlements" in st.session_state:
            with st.expander("🏦 Latest settlements (from API)", expanded=False):
                st.dataframe(
                    st.session_state["rzp_settlements"].head(50),
                    use_container_width=True,
                    hide_index=True,
                )

        st.markdown(
            "🔑 **Get test keys:** "
            "[https://dashboard.razorpay.com/app/keys]"
            "(https://dashboard.razorpay.com/app/keys) — use the **Test Mode** toggle."
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Razorpay client unavailable: {exc}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

result = st.session_state.get("result")
forecast = st.session_state.get("forecast")
gst = st.session_state.get("gst")

if result is None:
    st.info("👈 Click **Run Reconciliation** in the sidebar to start.")
    st.markdown("""
    ### What this does

    - **Loads** 4 sources: Razorpay settlement, bank statement, OMS orders, GST invoices
    - **Reconciles** Tier 1 (exact UTR / transaction_id match) + Tier 2 (fuzzy)
    - **Classifies** every exception into 10 categories with reason + action
    - **Forecasts** 13-week cash flow with low-balance alert
    - **Matches GST** invoices to payments (6 dimensions, ITC claimed vs eligible)
    - **Q&A agent** answers questions like "Why is pay_S30006 short?" with cited source rows

    ### Demo flow

    1. Click **Run Reconciliation** in the sidebar (3-5 sec)
    2. See the 4 KPIs and exception breakdown
    3. Scroll through the tabs: Reconciliation / Forecast / GST / Q&A / Exceptions
    4. Try the Q&A tab with: *"Why is pay_S30006 short?"*
    """)
else:
    # =====================================================================
    # Top KPIs
    # =====================================================================
    m = result.metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Match Rate", f"{m.get('match_rate', 0):.1%}")
    col2.metric("Payments Matched", m.get("tier1_matched_payments", 0))
    col3.metric("Exceptions", m.get("tier1_exceptions", 0))
    col4.metric("Bank Credits", m.get("bank_credits", 0))
    col5.metric("GST Invoices", m.get("gst_invoices", 0))

    st.markdown("---")

    # =====================================================================
    # Download reports
    # =====================================================================
    st.subheader("📤 Download reports")
    st.caption("Export the full reconciliation result as a multi-sheet Excel workbook or a polished PDF.")
    dl_col1, dl_col2, dl_col3 = st.columns([1, 1, 4])
    with dl_col1:
        try:
            tmp_xlsx = Path(tempfile.gettempdir()) / f"reconciliation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            export_excel(result, tmp_xlsx)
            xlsx_bytes = tmp_xlsx.read_bytes()
            tmp_xlsx.unlink(missing_ok=True)
            st.download_button(
                label="📥 Download Excel Report",
                data=xlsx_bytes,
                file_name=f"reconciliation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Excel export failed: {e}")
    with dl_col2:
        try:
            tmp_pdf = Path(tempfile.gettempdir()) / f"reconciliation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            export_pdf_report(result, tmp_pdf)
            pdf_bytes = tmp_pdf.read_bytes()
            tmp_pdf.unlink(missing_ok=True)
            st.download_button(
                label="📥 Download PDF Report",
                data=pdf_bytes,
                file_name=f"reconciliation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"PDF export failed: {e}")

    st.markdown("---")

    # =====================================================================
    # Tabs
    # =====================================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📊 Reconciliation", "💵 Cash Forecast", "🧾 GST Match", "💬 Q&A Agent", "⚠️ Exceptions"]
    )

    # ---- TAB 1: Reconciliation ----
    with tab1:
        st.subheader("Source comparison")
        st.caption("Each card summarises one of the 4 input sources.")

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Razorpay Settlements", m.get("razorpay_payments", 0), help="Payments + refunds")
            st.metric("OMS Orders", m.get("oms_orders", 0))
        with c2:
            st.metric("Bank Credits", m.get("bank_credits", 0))
            st.metric("GST Invoices", m.get("gst_invoices", 0))

        st.subheader("Match funnel")
        st.markdown(f"""
        - **Tier 1 (deterministic):** {m.get('tier1_matched_payments', 0)} / {m.get('razorpay_payments', 0)} Razorpay payments matched
        - **Tier 1 match attempts:** {m.get('tier1_match_attempts', 0)} (each payment tried against bank, OMS, GST)
        - **Tier 2 (fuzzy):** scheduled for residual records with rapidfuzz + tolerance
        - **Tier 3 (LLM):** scheduled for unresolvable cases with confidence gate
        """)

        if gst is not None:
            st.markdown("---")
            st.subheader("GST line match (6 dimensions)")
            gm = gst.metrics
            gc1, gc2, gc3, gc4 = st.columns(4)
            gc1.metric("Invoices matched", gm["gst_matched"])
            gc2.metric("Mismatches", gm["gst_mismatches"])
            gc3.metric("Missing invoices", gm["gst_missing"])
            gc4.metric("At-risk ITC", f"Rs {gm['at_risk_itc']:,.2f}")

    # ---- TAB 2: Cash Forecast ----
    with tab2:
        if forecast is None:
            st.info("Run reconciliation to see forecast.")
        else:
            st.subheader("13-week cash flow projection")
            fc1, fc2, fc3, fc4 = st.columns(4)
            fc1.metric("Opening balance", f"Rs {forecast.opening_balance:,.2f}")
            fc2.metric("Closing balance", f"Rs {forecast.closing_balance:,.2f}")
            fc3.metric("Lowest balance", f"Rs {forecast.lowest_balance:,.2f}", help=f"Week {forecast.lowest_week}")
            fc4.metric("Net Δ", f"Rs {forecast.total_inflow - forecast.total_outflow:,.2f}")

            if forecast.alert:
                st.warning(f"⚠️ {forecast.alert}")

            # Chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=forecast.df["week"],
                y=forecast.df["closing"],
                mode="lines+markers",
                name="Closing balance",
                line=dict(color="#10b981", width=3),
                fill="tozeroy",
                fillcolor="rgba(16,185,129,0.1)",
            ))
            fig.add_trace(go.Bar(
                x=forecast.df["week"],
                y=forecast.df["inflow"],
                name="Inflow",
                marker_color="#3b82f6",
                opacity=0.6,
            ))
            fig.add_trace(go.Bar(
                x=forecast.df["week"],
                y=-forecast.df["outflow"],
                name="Outflow",
                marker_color="#ef4444",
                opacity=0.6,
            ))
            fig.update_layout(
                title="13-Week Cash Forecast",
                xaxis_title="Week",
                yaxis_title="Rs",
                barmode="overlay",
                hovermode="x unified",
                height=500,
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📋 Weekly details"):
                st.dataframe(forecast.df, use_container_width=True, hide_index=True)

    # ---- TAB 3: GST Match ----
    with tab3:
        if gst is None:
            st.info("Run reconciliation to see GST match.")
        else:
            st.subheader("GST line match — 6 dimensions")
            st.markdown("""
            - **GSTIN** (15-char alphanumeric) — exact
            - **Invoice number** — exact
            - **Invoice date** — exact
            - **Taxable value** — ±Rs 1 tolerance
            - **Tax breakup** (CGST+SGST or IGST) — ±Rs 1 tolerance
            - **HSN/SAC code** — flagged if missing
            """)

            gc1, gc2, gc3 = st.columns(3)
            gc1.metric("ITC Claimed", f"Rs {gst.itc_claimed:,.2f}")
            gc2.metric("ITC Eligible", f"Rs {gst.itc_eligible:,.2f}")
            delta = gst.itc_eligible - gst.itc_claimed
            gc3.metric("At-risk ITC", f"Rs {gst.at_risk_itc:,.2f}", delta=f"Rs {delta:,.2f}")

            if not gst.mismatches.empty:
                st.markdown("---")
                st.subheader("❌ Mismatches")
                st.dataframe(
                    gst.mismatches[["payment_id", "invoice_no", "issues"]].head(20),
                    use_container_width=True,
                    hide_index=True,
                )

            if not gst.missing_invoices.empty:
                st.markdown("---")
                st.subheader("⚠️ Missing GST invoices")
                st.dataframe(
                    gst.missing_invoices[["payment_id"]].head(20),
                    use_container_width=True,
                    hide_index=True,
                )

    # ---- TAB 4: Q&A Agent ----
    with tab4:
        st.subheader("💬 Settlement Q&A Agent")
        st.caption("Ask in natural language. The agent cites source rows + shows the math.")

        # Suggested questions
        st.markdown("**Try:**")
        suggestions = [
            "Why is pay_S30006 short?",
            "Why is pay_S30000 short?",
            "Show reconciliation summary",
            "List all exceptions",
            "List missing_bank_credit exceptions",
            "Show fee variance",
        ]
        cols = st.columns(3)
        for i, q in enumerate(suggestions):
            with cols[i % 3]:
                if st.button(q, key=f"suggest_{i}", use_container_width=True):
                    st.session_state["pending_q"] = q

        # Chat history
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        # Display history
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Input
        pending = st.session_state.pop("pending_q", None)
        user_input = st.chat_input("Ask a finance question…")
        question = pending or user_input

        if question:
            # Add to history
            st.session_state.chat_history.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)

            # Get answer
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
            # Donut chart
            fig = px.pie(
                values=list(cats.values()),
                names=list(cats.keys()),
                hole=0.5,
                title="Exception breakdown",
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=450)
            col_a, col_b = st.columns([1, 1])
            with col_a:
                st.plotly_chart(fig, use_container_width=True)
            with col_b:
                # Bar chart
                fig2 = px.bar(
                    x=list(cats.keys()),
                    y=list(cats.values()),
                    title="Counts by category",
                    labels={"x": "Category", "y": "Count"},
                )
                fig2.update_layout(height=450, xaxis_tickangle=-30)
                st.plotly_chart(fig2, use_container_width=True)

            st.markdown("---")
            st.subheader("📋 Exception details")
            st.dataframe(
                result.exceptions.fillna("—"),
                use_container_width=True,
                height=400,
            )
        else:
            st.success("No exceptions — clean reconciliation! ✅")

        st.markdown("---")
        st.subheader("📖 Exception taxonomy (10 categories)")
        st.markdown("""
        | Category | Trigger | Suggested action |
        |---|---|---|
        | `missing_bank_credit` | Razorpay settled, bank no UTR | Wait 24h; raise with Razorpay support |
        | `orphan_bank_credit` | Bank credit, no Razorpay UTR | Investigate; log to suspense ledger |
        | `amount_mismatch` | UTR matches, amount differs > Rs 0.05 | Compare fee schedule; raise dispute |
        | `oms_amount_mismatch` | Razorpay ≠ OMS total | Reconcile cart; refund/adjust OMS |
        | `missing_oms_order` | Razorpay payment, no OMS | Investigate; possibly fraud |
        | `ghost_oms_order` | OMS paid, no Razorpay payment | Verify with customer; flag fraud |
        | `cancelled_order_with_payment` | OMS cancelled, Razorpay captured | Initiate refund via API |
        | `fee_rate_variance` | Razorpay fee ≠ contracted MDR | Update fee schedule; raise with AM |
        | `gst_amount_mismatch` | Invoice total ≠ Razorpay | Regenerate invoice; fix tax engine |
        | `missing_gst_invoice` | Payment, no GST invoice | Generate invoice; late-file if past |
        """)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown(
    "🔗 [github.com/AdityaST93/razorpay-finance-controller]"
    "(https://github.com/AdityaST93/razorpay-finance-controller) · "
    "Built for Razorpay AI Buildathon Track 4 · MIT License"
)
