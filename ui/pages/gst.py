"""
ui.pages.gst — 6-dimension GST line match.

Reads from `st.session_state["gst"]` and renders:
  - 3 KPI cards (ITC claimed, eligible, at-risk)
  - Matched invoices table
  - Mismatches with reasons
  - Missing invoices
  - 6-dimension match breakdown
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.design_system import kpi_card, section_header, style_plotly


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_gst(gst: Any):
    return gst


def _dims_table() -> pd.DataFrame:
    """The 6 dimensions the match engine checks."""
    return pd.DataFrame([
        ("1", "Supplier GSTIN",      "15-char alphanumeric", "Mismatched supplier"),
        ("2", "Invoice number",      "Exact (normalized)",   "Missing invoice"),
        ("3", "Invoice date",        "Exact match",          "Date drift"),
        ("4", "Taxable value",       "± Rs 1 tolerance",     "Taxable value mismatch"),
        ("5", "Tax breakup",         "CGST+SGST or IGST",    "GST breakup mismatch"),
        ("6", "HSN/SAC code",        "Often missing",        "HSN code mismatch"),
    ], columns=["#", "Dimension", "Rule", "Failure mode"])


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_gst(gst: Any = None) -> None:
    """Render the GST page."""
    if gst is None:
        gst = st.session_state.get("gst")

    if gst is None:
        st.info("Run reconciliation in the sidebar first.")
        return

    # ------------------------------------------------------------------
    # 1) 3 KPI cards (ITC claimed, eligible, at-risk)
    # ------------------------------------------------------------------
    section_header(
        "GST line match — 6 dimensions",
        "Each Razorpay payment is checked against its GST invoice on 6 dimensions.",
    )

    itc_claimed = Decimal(gst.itc_claimed)
    itc_eligible = Decimal(gst.itc_eligible)
    at_risk = Decimal(gst.at_risk_itc)
    delta = itc_eligible - itc_claimed

    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown(
            kpi_card(
                "ITC claimed",
                f"Rs {itc_claimed:,.0f}",
                "eligible input credit",
            ),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            kpi_card(
                "ITC eligible",
                f"Rs {itc_eligible:,.0f}",
                "post-match",
                tone="green",
            ),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            kpi_card(
                "At-risk ITC",
                f"Rs {at_risk:,.2f}",
                f"Δ Rs {delta:,.2f}",
                tone="red",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 2) 6-dimension match breakdown
    # ------------------------------------------------------------------
    section_header(
        "Match dimensions",
        "The 6 dimensions checked per payment ↔ invoice pair.",
    )

    dims = _dims_table()
    st.dataframe(dims, use_container_width=True, hide_index=True, height=240)

    # Quick numeric breakdown of match status from gst.metrics
    gm = getattr(gst, "metrics", {}) or {}
    matched_n = int(gm.get("gst_matched", 0))
    mismatch_n = int(gm.get("gst_mismatches", 0))
    missing_n = int(gm.get("gst_missing", 0))

    if (matched_n + mismatch_n + missing_n) > 0:
        fig = px.pie(
            values=[matched_n, mismatch_n, missing_n],
            names=["Matched", "Mismatched", "Missing invoice"],
            hole=0.5,
            title="GST match breakdown",
            color_discrete_sequence=["#10b981", "#f59e0b", "#ef4444"],
        )
        fig.update_layout(height=320, title_font_size=16, showlegend=True)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        style_plotly(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 3) Matched invoices table
    # ------------------------------------------------------------------
    section_header(
        "Matched invoices",
        "Payments with a clean match across all 6 dimensions.",
    )

    matched_df = getattr(gst, "matched", pd.DataFrame())
    if matched_df is None or matched_df.empty:
        st.info("No matched invoices yet.")
    else:
        cols = [c for c in [
            "payment_id", "invoice_no", "taxable_value", "cgst", "sgst", "igst",
            "total", "amount", "match_status", "issues",
        ] if c in matched_df.columns]
        st.caption(f"Showing {min(len(matched_df), 50):,} of {len(matched_df):,} matched rows.")
        st.dataframe(
            matched_df[cols].head(50).fillna("—"),
            use_container_width=True,
            hide_index=True,
            height=320,
        )

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 4) Mismatches with reasons
    # ------------------------------------------------------------------
    section_header(
        "Mismatches with reasons",
        "Payments that joined an invoice but failed at least one dimension.",
    )

    mismatches_df = getattr(gst, "mismatches", pd.DataFrame())
    if mismatches_df is None or mismatches_df.empty:
        st.success("No mismatches. Clean alignment.")
    else:
        cols = [c for c in [
            "payment_id", "invoice_no", "taxable_value", "cgst", "sgst", "igst",
            "total", "amount", "match_status", "issues",
        ] if c in mismatches_df.columns]
        st.caption(f"Showing {min(len(mismatches_df), 50):,} of {len(mismatches_df):,} mismatch rows.")
        st.dataframe(
            mismatches_df[cols].head(50).fillna("—"),
            use_container_width=True,
            hide_index=True,
            height=320,
        )

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 5) Missing invoices
    # ------------------------------------------------------------------
    section_header(
        "Missing invoices",
        "Payments that have no GST invoice linked. Late-file to recover ITC.",
    )

    missing_df = getattr(gst, "missing_invoices", pd.DataFrame())
    if missing_df is None or missing_df.empty:
        st.success("No missing invoices. Every payment has an invoice.")
    else:
        cols = [c for c in [
            "payment_id", "amount", "method", "created_at", "match_status",
        ] if c in missing_df.columns]
        st.caption(f"Showing {min(len(missing_df), 50):,} of {len(missing_df):,} missing rows.")
        st.dataframe(
            missing_df[cols].head(50).fillna("—"),
            use_container_width=True,
            hide_index=True,
            height=320,
        )
