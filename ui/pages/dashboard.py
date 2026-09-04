"""
ui.pages.dashboard — top-level KPI + exception overview page.

Reads from `st.session_state["result"]` and renders:
  - 5 large KPI cards in a row
  - 2-column layout: exception donut + bar (left), top 5 details (right)
  - Recent activity timeline (5 mock items from result.exceptions)
  - A "Re-run" button
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui.design_system import kpi_card, section_header, style_plotly


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_metrics(result: Any) -> dict:
    """Return metrics dict or sensible defaults if missing."""
    if result is None:
        return {}
    m = getattr(result, "metrics", None)
    if isinstance(m, dict):
        return m
    return {}


def _format_inr(x: float) -> str:
    try:
        return f"Rs {float(x):,.2f}"
    except Exception:
        return "Rs 0.00"


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_dashboard(result: Any = None) -> None:
    """Render the dashboard page.

    Parameters
    ----------
    result : core.reconcile.ReconcileResult | None
        The reconciled result. If None, falls back to
        ``st.session_state.get("result")``.
    """
    if result is None:
        result = st.session_state.get("result")

    # Empty state ----------------------------------------------------------
    if result is None:
        st.markdown(
            kpi_card("No data", "Run reconciliation", "to see KPIs", tone="amber"),
            unsafe_allow_html=True,
        )
        st.info("Hit Run Reconciliation in the sidebar to populate the dashboard.")
        return

    m = _safe_metrics(result)
    match_rate = float(m.get("match_rate", 0)) * 100
    n_payments = int(m.get("razorpay_payments", 0))
    n_matched = int(m.get("tier1_matched_payments", 0))
    n_clean = int(m.get("clean_payments", 0))
    n_excs = int(m.get("tier1_exceptions", 0))
    n_bank = int(m.get("bank_credits", 0))
    n_gst = int(m.get("gst_invoices", 0))

    # ------------------------------------------------------------------
    # Row 1 — five large KPI cards
    # ------------------------------------------------------------------
    section_header(
        "Reconciliation health",
        "Top-level metrics across the 4 source files.",
    )

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(
            kpi_card(
                "Match rate",
                f"{match_rate:.1f}%",
                f"{n_clean}/{n_payments} clean",
                tone="green",
            ),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            kpi_card(
                "Payments",
                f"{n_payments:,}",
                f"{n_matched} matched",
            ),
            unsafe_allow_html=True,
        )
    with k3:
        exc_tone = "amber" if 0 < n_excs < 10 else ("red" if n_excs >= 10 else "green")
        st.markdown(
            kpi_card(
                "Exceptions",
                f"{n_excs:,}",
                "categorised",
                tone=exc_tone,
            ),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            kpi_card(
                "Bank credits",
                f"{n_bank:,}",
                "verified",
            ),
            unsafe_allow_html=True,
        )
    with k5:
        st.markdown(
            kpi_card(
                "GST invoices",
                f"{n_gst:,}",
                "matched",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1.2rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Row 2 — 2 columns: donut + bar (left), top 5 details (right)
    # ------------------------------------------------------------------
    section_header(
        "Exception breakdown",
        "Where the failures cluster, and the worst offenders.",
    )

    cats = m.get("exception_categories", {}) or {}
    left, right = st.columns([3, 2])

    with left:
        if cats:
            l1, l2 = st.columns(2)
            with l1:
                # Donut
                fig = px.pie(
                    values=list(cats.values()),
                    names=list(cats.keys()),
                    hole=0.55,
                    title="By category",
                )
                fig.update_traces(
                    textposition="inside",
                    textinfo="percent+label",
                    marker=dict(
                        colors=["#3395ff", "#00d4ff", "#10b981", "#f59e0b",
                                "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4",
                                "#84cc16", "#f97316"],
                    ),
                )
                fig.update_layout(height=380, showlegend=False, title_font_size=16)
                style_plotly(fig)
                st.plotly_chart(fig, use_container_width=True)
            with l2:
                # Horizontal bar
                fig2 = px.bar(
                    x=list(cats.values()),
                    y=list(cats.keys()),
                    orientation="h",
                    title="Counts",
                    labels={"x": "Count", "y": "Category"},
                    color=list(cats.values()),
                    color_continuous_scale=["#3395ff", "#00d4ff"],
                )
                fig2.update_layout(
                    height=380,
                    yaxis=dict(autorange="reversed"),
                    coloraxis_showscale=False,
                    title_font_size=16,
                )
                style_plotly(fig2)
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.success("No exceptions. Clean reconciliation.")

    with right:
        st.markdown("##### Top 5 exception details")
        try:
            ex = getattr(result, "exceptions", pd.DataFrame())
            if ex is None or ex.empty:
                st.success("No exceptions to show.")
            else:
                cols_to_show = [
                    c for c in ["payment_id", "exception_category", "reason", "amount"]
                    if c in ex.columns
                ]
                top5 = ex[cols_to_show].head(5)
                st.dataframe(top5, use_container_width=True, hide_index=True, height=300)
        except Exception as e:
            st.warning(f"Could not render exception details: {e}")

    st.markdown("<div style='height: 1.2rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Row 3 — Recent activity timeline (5 mock items)
    # ------------------------------------------------------------------
    section_header(
        "Recent activity",
        "Last 5 events from the reconciliation run.",
    )

    # Build a 5-item mock timeline from result.exceptions
    items = []
    try:
        ex = getattr(result, "exceptions", pd.DataFrame())
        if ex is not None and not ex.empty:
            for _, row in ex.head(5).iterrows():
                items.append({
                    "ts": row.get("created_at", row.get("date", datetime.now().strftime("%Y-%m-%d"))),
                    "category": row.get("exception_category", "exception"),
                    "reason": row.get("reason", "Uncategorised exception"),
                    "payment_id": row.get("payment_id", row.get("utr", "—")),
                })
        else:
            items = [{"ts": datetime.now().strftime("%Y-%m-%d"),
                      "category": "clean",
                      "reason": "Reconciliation complete with no exceptions",
                      "payment_id": "—"}]
    except Exception:
        items = [{"ts": datetime.now().strftime("%Y-%m-%d"),
                  "category": "info",
                  "reason": "Unable to load activity log",
                  "payment_id": "—"}]

    timeline_html = '<div class="rp-glass" style="padding:1rem 1.2rem;">'
    for it in items:
        ts = it.get("ts", "")
        cat = it.get("category", "exception")
        reason = it.get("reason", "")
        pid = it.get("payment_id", "—")
        timeline_html += (
            f'<div style="display:flex; align-items:flex-start; gap:12px; '
            f'padding:0.55rem 0; border-bottom:1px solid rgba(15,23,42,0.06);">'
            f'<div style="min-width:96px; font-family:JetBrains Mono,monospace; '
            f'color:#64748b; font-size:0.78rem;">{ts}</div>'
            f'<div style="flex:1;">'
            f'<div style="font-weight:600; color:#0f172a; font-size:0.92rem;">'
            f'{cat}</div>'
            f'<div style="color:#475569; font-size:0.85rem;">{reason}</div>'
            f'</div>'
            f'<div style="font-family:JetBrains Mono,monospace; color:#3395ff; '
            f'font-size:0.82rem;">{pid}</div>'
            f'</div>'
        )
    timeline_html += "</div>"
    st.markdown(timeline_html, unsafe_allow_html=True)

    st.markdown("<div style='height: 1.2rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Row 4 — Re-run button
    # ------------------------------------------------------------------
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        if st.button("Re-run reconciliation", type="primary", use_container_width=True):
            with st.spinner("Re-running reconciliation..."):
                try:
                    from core.reconcile import run_reconciliation
                    from core.forecast import forecast_cash
                    from core.tax_match import match_gst
                    new_result = run_reconciliation()
                    new_forecast = forecast_cash()
                    new_gst = match_gst()
                    st.session_state["result"] = new_result
                    st.session_state["forecast"] = new_forecast
                    st.session_state["gst"] = new_gst
                    st.success("Reconciliation re-run complete.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Re-run failed: {e}")
