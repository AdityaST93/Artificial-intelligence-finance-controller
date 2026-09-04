"""
ui.pages.reconciliation — source comparison + tier funnel + tables.

Reads from `st.session_state["result"]` and renders:
  - 4 source comparison cards
  - Tier-by-tier funnel visualization
  - Matched records table (first 20)
  - Exception records table (all)
  - Download button for matched records as CSV
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.design_system import kpi_card, section_header, style_plotly


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_metrics(result: Any) -> dict:
    if result is None:
        return {}
    m = getattr(result, "metrics", None)
    return m if isinstance(m, dict) else {}


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_reconciliation(result: Any = None) -> None:
    """Render the reconciliation page.

    Parameters
    ----------
    result : core.reconcile.ReconcileResult | None
    """
    if result is None:
        result = st.session_state.get("result")

    if result is None:
        st.info("Run reconciliation in the sidebar first.")
        return

    m = _safe_metrics(result)

    # ------------------------------------------------------------------
    # 1) Source comparison cards (4 sources, count each)
    # ------------------------------------------------------------------
    section_header(
        "Source comparison",
        "Each source feeds the reconciliation engine.",
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            kpi_card(
                "Razorpay",
                f"{int(m.get('razorpay_payments', 0)):,}",
                "payments + refunds",
            ),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            kpi_card(
                "Bank",
                f"{int(m.get('bank_credits', 0)):,}",
                "settled credits",
            ),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            kpi_card(
                "OMS",
                f"{int(m.get('oms_orders', 0)):,}",
                "internal orders",
            ),
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            kpi_card(
                "GST",
                f"{int(m.get('gst_invoices', 0)):,}",
                "tax invoices",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 2) Tier-by-tier funnel visualization
    # ------------------------------------------------------------------
    section_header(
        "Tier-by-tier funnel",
        "Deterministic → fuzzy → LLM. The funnel narrows with each tier.",
    )

    n_payments = int(m.get("razorpay_payments", 0))
    n_t1_matched = int(m.get("tier1_matched_payments", 0))
    n_clean = int(m.get("clean_payments", 0))
    n_excs = int(m.get("tier1_exceptions", 0))

    # Funnel data: Tier 1 attempted → Tier 1 matched → clean → exceptions
    funnel_rows = [
        ("Input (Razorpay payments)", n_payments, "#3395ff"),
        ("Tier 1 (deterministic)", n_t1_matched, "#00d4ff"),
        ("Clean (no exception anywhere)", n_clean, "#10b981"),
        ("Exceptions (named & categorised)", n_excs, "#f59e0b"),
    ]

    funnel_html = '<div class="rp-glass" style="padding:1.2rem;">'
    max_count = max((r[1] for r in funnel_rows), default=1) or 1
    for label, count, color in funnel_rows:
        width_pct = (count / max_count) * 100 if max_count else 0
        funnel_html += (
            f'<div style="margin-bottom:0.85rem;">'
            f'<div style="display:flex; justify-content:space-between; '
            f'font-size:0.85rem; color:#334155; margin-bottom:4px;">'
            f'<span style="font-weight:600;">{label}</span>'
            f'<span style="font-family:JetBrains Mono,monospace; color:#0f172a;">{count:,}</span>'
            f'</div>'
            f'<div style="height:18px; background:rgba(15,23,42,0.05); border-radius:9px; overflow:hidden;">'
            f'<div style="height:100%; width:{width_pct:.1f}%; background:linear-gradient(90deg, {color}, {color}cc); '
            f'border-radius:9px; transition:width .4s ease;"></div>'
            f'</div>'
            f'</div>'
        )
    funnel_html += "</div>"
    st.markdown(funnel_html, unsafe_allow_html=True)

    # Funnel narrative
    st.markdown(
        f"""
        - **Tier 1 (deterministic pandas):** joined Razorpay settlements against bank UTRs,
          OMS `transaction_id`s, and GST `razorpay_payment_id`s. **{n_t1_matched}** payments
          got at least one match.
        - **Tier 2 (fuzzy, rapidfuzz):** reserved for residue — dates off by ±2 days,
          amounts within ±Rs 0.05 tolerance, fuzzy name match.
        - **Tier 3 (LLM, OpenRouter):** never on the happy path. Used only when both
          Tier 1 and Tier 2 fail, with a confidence gate ≥ 0.7.
        - **Below the gate:** **{n_excs}** honest exceptions, every one named and categorised.
        """
    )

    st.markdown("<div style='height: 1.2rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 3) Matched records table (first 20) + download button
    # ------------------------------------------------------------------
    section_header(
        "Matched records",
        "First 20 records that passed all tier-1 deterministic checks.",
    )

    matched_df = getattr(result, "df", pd.DataFrame())
    if matched_df is None or matched_df.empty:
        st.info("No matched records.")
    else:
        # Pick reasonable columns
        cols = [c for c in [
            "payment_id", "order_receipt", "amount", "fee", "tax", "credit",
            "utr", "bank_credit", "transaction_id", "order_id", "order_status",
            "razorpay_payment_id", "invoice_no", "total", "tier", "status", "reason",
        ] if c in matched_df.columns]
        st.dataframe(
            matched_df[cols].head(20),
            use_container_width=True,
            hide_index=True,
            height=420,
        )

        st.download_button(
            label="Download matched records (CSV)",
            data=_df_to_csv_bytes(matched_df),
            file_name=f"matched_records_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            type="primary",
        )

    st.markdown("<div style='height: 1.2rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 4) Exception records table (all)
    # ------------------------------------------------------------------
    section_header(
        "Exception records",
        "All unresolvable records, named and categorised.",
    )

    ex_df = getattr(result, "exceptions", pd.DataFrame())
    if ex_df is None or ex_df.empty:
        st.success("No exceptions. Clean reconciliation.")
    else:
        st.caption(f"Showing all {len(ex_df):,} exception rows.")
        st.dataframe(
            ex_df.fillna("—"),
            use_container_width=True,
            hide_index=True,
            height=420,
        )
