"""
ui.pages.exceptions — taxonomy + breakdown + filterable exception list.

Reads from `st.session_state["result"]` and renders:
  - Exception taxonomy table (10 categories)
  - Donut chart of exception breakdown
  - Horizontal bar chart of counts
  - Full exception DataFrame
  - Category filter dropdown
  - Search box for payment_id
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.design_system import kpi_card, section_header, style_plotly


# ---------------------------------------------------------------------------
# Exception taxonomy (10 categories)
# ---------------------------------------------------------------------------

EXCEPTION_TAXONOMY: list[tuple[str, str, str]] = [
    # (code, category, short description)
    ("EX01", "utr_mismatch",        "UTR does not match any Razorpay payment"),
    ("EX02", "amount_mismatch",     "Settled amount differs from payment by more than tolerance"),
    ("EX03", "date_drift",          "Bank credit date >2 days from payment date"),
    ("EX04", "oms_ghost",           "Order has no Razorpay payment (chargeback / abandoned)"),
    ("EX05", "oms_unsettled",       "Order created but payment never settled"),
    ("EX06", "bank_orphan",         "Bank credit without a matching Razorpay payment"),
    ("EX07", "gst_mismatch",        "GST invoice does not match payment on one of 6 dimensions"),
    ("EX08", "missing_invoice",     "Payment has no GST invoice linked"),
    ("EX09", "duplicate_utr",       "Same UTR appears in multiple Razorpay settlements"),
    ("EX10", "fx_or_refund",        "Refunds or FX conversions outside tolerance"),
]


def _taxonomy_table() -> pd.DataFrame:
    return pd.DataFrame(
        EXCEPTION_TAXONOMY,
        columns=["Code", "Category", "Description"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_metrics(result: Any) -> dict:
    if result is None:
        return {}
    m = getattr(result, "metrics", None)
    return m if isinstance(m, dict) else {}


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Make sure the dataframe has the columns we filter on."""
    out = df.copy()
    if "exception_category" not in out.columns and "category" in out.columns:
        out["exception_category"] = out["category"]
    if "exception_category" not in out.columns and "reason" in out.columns:
        # Try to derive a category from the reason text (best-effort)
        out["exception_category"] = out["reason"].fillna("uncategorised")
    if "exception_category" not in out.columns:
        out["exception_category"] = "uncategorised"
    if "payment_id" not in out.columns:
        out["payment_id"] = out.index.astype(str)
    return out


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_exceptions(result: Any = None) -> None:
    """Render the exceptions page."""
    if result is None:
        result = st.session_state.get("result")

    if result is None:
        st.info("Run reconciliation in the sidebar first.")
        return

    m = _safe_metrics(result)
    n_excs = int(m.get("tier1_exceptions", 0))
    cats = m.get("exception_categories", {}) or {}

    # ------------------------------------------------------------------
    # 1) Top-of-page KPI cards
    # ------------------------------------------------------------------
    section_header(
        "Exception explorer",
        "Browse, filter, and inspect every named exception.",
    )

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            kpi_card(
                "Total exceptions",
                f"{n_excs:,}",
                "named & categorised",
                tone="amber" if n_excs > 0 else "green",
            ),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            kpi_card(
                "Categories",
                f"{len(cats):,}",
                "distinct labels",
            ),
            unsafe_allow_html=True,
        )
    with k3:
        top_cat = max(cats, key=cats.get) if cats else "—"
        st.markdown(
            kpi_card(
                "Top category",
                top_cat,
                f"{cats.get(top_cat, 0):,}" if cats else "0",
                tone="red" if cats else "green",
            ),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            kpi_card(
                "Match rate",
                f"{float(m.get('match_rate', 0)) * 100:.1f}%",
                "overall",
                tone="green",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 2) Exception taxonomy (10 categories)
    # ------------------------------------------------------------------
    section_header(
        "Exception taxonomy",
        "The 10 named categories the engine uses to label exceptions.",
    )

    st.dataframe(
        _taxonomy_table(),
        use_container_width=True,
        hide_index=True,
        height=360,
    )

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 3) Donut + horizontal bar breakdown
    # ------------------------------------------------------------------
    section_header(
        "Exception breakdown",
        "Counts by category.",
    )

    if cats:
        c1, c2 = st.columns(2)
        with c1:
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
            fig.update_layout(height=420, showlegend=False, title_font_size=16)
            style_plotly(fig)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
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
                height=420,
                yaxis=dict(autorange="reversed"),
                coloraxis_showscale=False,
                title_font_size=16,
            )
            style_plotly(fig2)
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.success("No exceptions. Clean reconciliation.")

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 4) Filter + search controls
    # ------------------------------------------------------------------
    section_header(
        "Exception records",
        "Filter by category, search by payment_id.",
    )

    ex_df = getattr(result, "exceptions", pd.DataFrame())
    if ex_df is None or ex_df.empty:
        st.success("No exception rows to display.")
        return

    ex_df = _ensure_columns(ex_df)

    # Filter row
    fc1, fc2 = st.columns([1, 2])
    with fc1:
        # All categories from taxonomy + any extra in data
        all_cats = sorted(set(EXCEPTION_TAXONOMY_CODE_LOOKUP := {
            c for c in EXCEPTION_TAXONOMY[0][1:] for c in [c[1]]  # noqa: F841
        }.union(ex_df["exception_category"].dropna().unique().tolist())))
        # Build a clean option list
        all_cats = sorted(set(
            [c[1] for c in EXCEPTION_TAXONOMY] +
            ex_df["exception_category"].dropna().astype(str).unique().tolist()
        ))
        cat_choice = st.selectbox(
            "Category filter",
            options=["(all)"] + all_cats,
            key="exceptions_category",
        )
    with fc2:
        search = st.text_input(
            "Search by payment_id",
            value="",
            placeholder="e.g. pay_ABC123…",
            key="exceptions_search",
        )

    # Apply filters
    filtered = ex_df.copy()
    if cat_choice and cat_choice != "(all)":
        filtered = filtered[filtered["exception_category"] == cat_choice]
    if search and search.strip():
        s = search.strip().lower()
        filtered = filtered[
            filtered["payment_id"].astype(str).str.lower().str.contains(s, na=False)
        ]

    st.caption(f"Showing {len(filtered):,} of {len(ex_df):,} exception rows.")
    st.dataframe(
        filtered.fillna("—"),
        use_container_width=True,
        hide_index=True,
        height=420,
    )
